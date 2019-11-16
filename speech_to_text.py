from google.cloud import speech_v1p1beta1
import io
import sys

def sample_recognize(local_file_path):
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
    print(u"Transcript: {}".format(alternative.transcript))
    # Print the start and end time of each word
    for word in alternative.words:
        print(u"Word: {}".format(word.word))
        print(u"Confidence: {}".format(word.confidence))
        print(
            u"Start time: {} seconds {} nanos".format(
                word.start_time.seconds, word.start_time.nanos
            )
        )
        print(
            u"End time: {} seconds {} nanos".format(
                word.end_time.seconds, word.end_time.nanos
            )
        )
    return alternative
