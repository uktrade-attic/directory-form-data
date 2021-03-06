import signal

from django.conf import settings

import boto3
import botocore


class AwsErrorCodes:
    SQS_NON_EXISTENT_QUEUE = 'AWS.SimpleQueueService.NonExistentQueue'
    SIGNATURE_DOES_NOT_MATCH = 'SignatureDoesNotMatch'


class AwsError:
    codes = AwsErrorCodes()

    @staticmethod
    def is_error(exception, error_code):
        """Returns True if exception is boto's error with given code

        Args:
            exception (Exception): boto client exception
            error_code (string): AWS error code

        Returns:
            boolean: True if exception is boto's error with given code
        """
        if hasattr(exception, 'response'):
            error_code = exception.response.get('Error', {}).get('Code')
            return error_code == error_code

    @staticmethod
    def is_sqs_non_existent_queue(exception):
        """Returns True if exception is boto's
        AWS.SimpleQueueService.NonExistentQueue'

        Args:
            error (Exception): boto client exception

        Returns:
            boolean: True if exception is boto's 'NonExistentQueue'
        """
        return AwsError.is_error(
            exception=exception,
            error_code=AwsError.codes.SQS_NON_EXISTENT_QUEUE
        )

    @staticmethod
    def is_signature_does_not_match(exception):
        """Returns True if exception is boto's 'SignatureDoesNotMatch'

        Args:
            error (Exception): boto client exception

        Returns:
            boolean: True if exception is boto's 'SignatureDoesNotMatch'
        """
        return AwsError.is_error(
            exception=exception,
            error_code=AwsError.codes.SIGNATURE_DOES_NOT_MATCH
        )


class QueueService:
    """Form data queue service

    Attributes:
        queue (SQS.Queue): SQS queue
        queue_name (str): Name of the SQS queue
        sqs (boto3.resource): SQS connection
    """
    queue_name = ''

    def __init__(self):
        if not self.queue_name:
            raise NotImplementedError("queue_name cannot be empty")

        self.initialise_sqs()

    def initialise_sqs(self):
        self._sqs = boto3.resource('sqs', region_name=settings.SQS_REGION_NAME)
        self._queue = self.get_or_create_queue(name=self.queue_name)

    def get_or_create_queue(self, name):
        """Returns SQS queue by name, creates if it does not exist

        Args:
            name (str): Queue name

        Returns:
            SQS.Queue: Requested queue
        """
        try:
            queue = self._sqs.get_queue_by_name(QueueName=name)
        except botocore.exceptions.ClientError as error:
            if AwsError.is_sqs_non_existent_queue(error):
                queue = self._sqs.create_queue(QueueName=name)
            else:
                raise

        return queue

    def send(self, data):
        """Sends data to the queue

        Args:
            data (str): Data string
        """
        self._queue.send_message(MessageBody=data)

    def receive(
            self,
            wait_time_in_seconds=settings.SQS_WAIT_TIME,
            max_number_of_messages=settings.SQS_MAX_NUMBER_OF_MESSAGES):
        """Receive messages from the queue

        Args:
            wait_time_in_seconds (int, optional): Long polling period
            max_number_of_messages (int, optional): Number of messages to get

        Returns:
            list: List of SQS.Message
        """
        try:
            messages = self._queue.receive_messages(
                WaitTimeSeconds=wait_time_in_seconds,
                MaxNumberOfMessages=max_number_of_messages,
            )
        except botocore.exceptions.ClientError as error:
            # try to reinitialise sqs connection on 'Signature expired' error
            if AwsError.is_signature_does_not_match(error):
                self.initialise_sqs()
                messages = self._queue.receive_messages(
                    WaitTimeSeconds=wait_time_in_seconds,
                    MaxNumberOfMessages=max_number_of_messages,
                )

        return messages


class SignalReceiver:
    """Receives specified process signals

    Attributes:
        signals (tuple): Signals to receive
        received (list): Received signals
    """
    signals = ()

    def __init__(self):
        self.received = []

        for sig in self.signals:
            self.add_handler(sig)

    def add_handler(self, sig):
        """Adds a handler for a signal

        Args:
            sig (int): Signal to handle

        Returns:
            signal.signal: signal handler
        """
        return signal.signal(sig, self.add_to_received)

    def add_to_received(self, signum, frame):
        """Adds signal to received signals list"""
        self.received.append(signum)


class ExitSignalReceiver(SignalReceiver):
    """Receiver for exit signals"""
    signals = (signal.SIGINT, signal.SIGTERM)
