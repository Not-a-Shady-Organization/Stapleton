from google.cloud import speech_v1p1beta1
import io
import sys

def sample_recognize(local_file_path, log_filepath):
    """
    Print start and end time of each word spoken in audio file from Cloud Storage

    Args:
      storage_uri URI for audio file in Cloud Storage, e.g. gs://[BUCKET]/[FILE]
    """

    client = speech_v1p1beta1.SpeechClient()
    enable_word_time_offsets = True
    enable_word_confidence = True

    # The language of the supplied audio
    language_code = "en-US"
    config = {
        "enable_word_confidence": enable_word_confidence,
        "enable_word_time_offsets": enable_word_time_offsets,
        "language_code": language_code,
    }
    with io.open(local_file_path, "rb") as f:
        content = f.read()
    audio = {"content": content}

    response = client.recognize(config, audio)

    # The first result includes start and end time word offsets
    result = response.results[0]
    # First alternative is the most probable result
    alternative = result.alternatives[0]
    with open(log_filepath, 'a') as log:
        log.write(f'\nFile: {local_file_path}\n')
        log.write(f'transcription: {alternative.transcript}\n')

        for word in alternative.words:
            log.write(f'Word: {word.word}\n')
            log.write(f'Conf: {word.confidence}\n')
            log.write(
                u"Start time: {} seconds {} nanos\n".format(
                    word.start_time.seconds, word.start_time.nanos
                )
            )
            log.write(
                u"End time: {} seconds {} nanos\n".format(
                    word.end_time.seconds, word.end_time.nanos
                )
            )
    return alternative
