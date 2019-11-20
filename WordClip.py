from youtube_utils import video_to_flac, download_video, change_audio_speed
from google.cloud import speech_v1p1beta1
import io
import sys
import os
from pydub import AudioSegment
from pydub.playback import play
from subprocess import check_output


'''
Maybe it makes the most sense for a crop action to return a new WordClip
Each clip will have a video code, start time, end time, and speed. All Should
be accurate and self-contained.

A crop action will involve math now :(


So either I create a clip and it has no parent... which means it needs to download something
OR I create a clip and hand it the cropped audio I just made... however all clips know where
the raw clip is.


WE NEVER WANT VIDEO. We download it, only to scrape out the audio.. Then we only want it
back when we're finished


media/audio/{word}/attempt-{attempt}/{word}-raw.flac
media/audio/{word}/attempt-{attempt}/{word}-speed-{round(speed*100,2)}%-cropi-{crop_iteration}.flac
'''


directories = {
    'VIDEO_DIRECTORY': 'media/video',
    'AUDIO_DIRECTORY': 'media/audio'
}


class NoTranscriptionError(Exception):
    pass



def attempt_from_filepath(filepath):
    attempt = [x for x in filepath.split('/') if 'attempt' in x]
    return int(attempt[0].split('-')[-1])


def crop_iteration_from_filepath(audio_filepath):
    token = [x for x in audio_filepath.replace('.flac', '').split('/') if 'cropi' in x][0]
    return int(token.split('-')[token.split('-').index('cropi')+1])


def next_raw_audio_filepath(word, attempt, speed):
    raw_audio_directory = f"{directories['AUDIO_DIRECTORY']}/{word}/attempt-{attempt}"
    if not os.path.exists(raw_audio_directory):
        os.makedirs(raw_audio_directory)
    return f"{raw_audio_directory}/raw-{word}.flac"


def next_cropped_audio_filepath(word, attempt, speed):
    cropped_audio_directory = f"{directories['AUDIO_DIRECTORY']}/{word}/attempt-{attempt}"
    if not os.path.exists(cropped_audio_directory):
        os.makedirs(cropped_audio_directory)

    crop_iterations = [x for x in os.listdir(cropped_audio_directory) if f'raw-{word}' not in x]
    if crop_iterations == []:
        crop_iteration = 0
    else:
        print(crop_iterations)
        nums = [crop_iteration_from_filepath(filepath) for filepath in crop_iterations]
        crop_iteration = max(nums) + 1
    return f"{cropped_audio_directory}/{word}-cropi-{crop_iteration}-speed-{speed}.flac"


def next_raw_video_filepath(word):
    video_output_subdirectory = f"{directories['VIDEO_DIRECTORY']}/{word}"
    if not os.path.exists(video_output_subdirectory):
        os.makedirs(video_output_subdirectory)

    attempts = os.listdir(video_output_subdirectory)
    if attempts == []:
        attempt = 0
    else:
        nums = [attempt_from_filepath(video_output_subdirectory + '/' + x) for x in attempts if 'attempt' in x]
        attempt = max(nums) + 1
    os.makedirs(f"{video_output_subdirectory}/attempt-{attempt}")
    video_output_filepath = f"{video_output_subdirectory}/attempt-{attempt}/raw-{word}.mkv"

    return video_output_filepath




class WordClip():

    def __init__(self, word, video_code, start_time, end_time, logger=None, speed=1, raw_video_filepath=None, raw_audio_filepath=None, raw_clip_start_time=None, raw_clip_end_time=None, audio_filepath=None):
        # On generation one/raw clips, we download a video, then take the audio for operations.
        # On child generations, we operate only on audio, but we still learn about where the video is.

        # Check if we're the raw clip
        self.raw = not audio_filepath

        self.word = word
        self.video_code = video_code
        self.start_time = start_time    # Refers to the start and end time of the initially downloaded clip
        self.end_time = end_time
        self.speed = speed
        self.logger = logger

        # If we're the first generation, download the video
        if self.raw:
            self.raw_video_filepath = next_raw_video_filepath(word)
            buffer = 5
            download_video(video_code, start_time, end_time, self.raw_video_filepath, log_filepath=logger)
            self.start_time = start_time-buffer    # Refers to the start and end time of the initially downloaded clip
            self.end_time = end_time+buffer
            self._attempt = attempt_from_filepath(self.raw_video_filepath)
            self.raw_clip_start_time = self.start_time
            self.raw_clip_end_time = self.end_time
            self.raw_audio_filepath = next_raw_audio_filepath(word, self._attempt, self.speed)
            self.audio_filepath = self.raw_audio_filepath
            self._convert_raw_video_to_audio(self.audio_filepath)
            self._crop_iteration = None

        # Not the first generation, don't download, just note where things already are
        else:
            self.raw_video_filepath = raw_video_filepath
            self.raw_audio_filepath = raw_audio_filepath
            self.raw_clip_start_time = raw_clip_start_time
            self.raw_clip_end_time = raw_clip_end_time

            self._attempt = attempt_from_filepath(self.raw_video_filepath)
            self.audio_filepath = audio_filepath
            self._crop_iteration = crop_iteration_from_filepath(audio_filepath)

        self.length = self.end_time - self.start_time
        self._transcribe()


    def __iter__(self):
        yield from self.transcribed_word_strings

    # Wanted to return clip length, but it needs to be an int
    def __len__(self):
        return len(self.transcribed_word_strings)

    def __repr__(self):
        return  f'Video code: {self.video_code}\n' + \
                f'Link: https://www.youtube.com/watch?v={self.video_code}\n' + \
                f'Interval: ({self.start_time}, {self.end_time})\n' +\
                f'Transcript: {self.transcript}\n'

    def _convert_raw_video_to_audio(self, raw_audio_filepath):
        '''Converts raw video to audio. Only needs to be done in first generation constructor.'''
        video_to_flac(self.raw_video_filepath, raw_audio_filepath, self.logger)


    def play(self):
        sound = AudioSegment.from_file(self.audio_filepath)
        play(sound)


    def save(self):
        pass


    def _transcribe(self):
        client = speech_v1p1beta1.SpeechClient()
        enable_word_time_offsets = True
        enable_word_confidence = True
        language_code = "en-US"
        config = {
            "enable_word_confidence": enable_word_confidence,
            "enable_word_time_offsets": enable_word_time_offsets,
            "language_code": language_code,
        }
        with io.open(self.audio_filepath, "rb") as f:
            content = f.read()
        audio = {"content": content}

        response = client.recognize(config, audio)


        # TODO: We throw out alternatives and only use the first one.. they may be helpful

        # The first result includes start and end time word offsets
        try:
            result = response.results[0]
        except IndexError:
            self.transcription = None
            self.transcript = None
            self.transcribed_word_strings = []
            self.transcibed_words = []
            # raise NoTranscriptionError(f'No words were found in clip {self.audio_filepath}')
            return

        # First alternative is the most probable result
        alternative = result.alternatives[0]
        self.transcription = alternative
        self.transcript = alternative.transcript.lower()
        self.transcribed_word_strings = [w.word.lower() for w in alternative.words]
        self.transcibed_words = [w for w in alternative.words]


    def interval_of(self, word):
        if word.lower() not in [w.lower() for w in self.transcribed_word_strings]:
            return None

        for w in self.transcibed_words:
            if w.word.lower() == word.lower():
                start_time = float(str(w.start_time.seconds) + '.' + str(w.start_time.nanos))
                end_time = float(str(w.end_time.seconds) + '.' + str(w.end_time.nanos))
                return (start_time, end_time)


    def confidence_of(self, word):
        if word.lower() not in [w.lower() for w in self.transcribed_word_strings]:
            return None

        for w in self.transcibed_words:
            if w.word.lower() == word.lower():
                return w.confidence


    def change_speed(self, speed):
        new_audio_filepath = next_cropped_audio_filepath(self.word, self._attempt, speed)
        change_audio_speed(self.audio_filepath, speed, new_audio_filepath, log_filepath=self.logger)
        return WordClip(
            self.word,
            self.video_code,
            self.start_time,
            self.end_time,
            logger=self.logger,
            speed=speed,
            raw_video_filepath=self.raw_video_filepath,
            raw_audio_filepath=self.raw_audio_filepath,
            raw_clip_start_time=self.raw_clip_start_time,
            raw_clip_end_time=self.raw_clip_end_time,
            audio_filepath=new_audio_filepath
        )


    def crop(self, interval):
        '''Crops our audio file, adds the cropped audio to a directory, and creates a new WordClip to handle that audio file'''

        cropped_audio_filepath = next_cropped_audio_filepath(self.word, self._attempt, self.speed)

        crop_start_time, crop_end_time = interval
        clip_length = crop_end_time - crop_start_time

        print('cs', crop_start_time)
        print('ce', crop_end_time)
        print('st', self.start_time)
        print('et', self.end_time)


        with open(self.logger, 'a') as log:
            if clip_length > 0.1:
                # Should swap
                # Insanity in the numbers here lets us crop from the raw file
                cropping_command = f'ffmpeg -y -ss 0 -i {self.raw_audio_filepath} -ss {self.start_time+crop_start_time - self.raw_clip_start_time} -t {self.end_time+(crop_end_time-self.length) - (self.start_time+crop_start_time)} -c:a flac {cropped_audio_filepath}'
                print(cropping_command)
                check_output(cropping_command, shell=True, stderr=log)
            else:
                print("FUCK")


        # TODO: Proper calculations for start and end time need to be made & take speed into account
        return WordClip(
            self.word,
            self.video_code,
            self.start_time+crop_start_time,
            self.end_time+(crop_end_time-self.length),
            logger=self.logger,
            speed=self.speed,
            raw_video_filepath=self.raw_video_filepath,
            raw_audio_filepath=self.raw_audio_filepath,
            raw_clip_start_time=self.raw_clip_start_time,
            raw_clip_end_time=self.raw_clip_end_time,
            audio_filepath=cropped_audio_filepath
        )


    def crop_beginning(self, distance):
        '''Crops beginning of clip forward by distance seconds.'''
        pass


    def crop_end(self, distance):
        '''Crops end of clip backward by distance seconds. Negative numbers extend the clip.'''
        pass


    def get_matching_video(self):
        raw_audio_directory = f"{directories['VIDEO_DIRECTORY']}/{word}/attempt-{attempt}"
        video_filepath = f"{raw_audio_directory}/{word}.mkv"

        crop_start_time = self.start_time
        crop_end_time = self.end_time
        clip_length = crop_end_time - crop_start_time

        with open(self.logger, 'a') as log:
            if clip_length > 0:
                cropping_command = f'ffmpeg -y -ss 0 -i {self.raw_video_filepath} -ss {crop_start_time} -t {crop_end_time - crop_start_time} -c:v libx264 -c:a flac {video_filepath}'
                check_output(cropping_command, shell=True, stderr=log)


        print(video_filepath)
        return video_filepath



if __name__ == '__main__':
    clip = WordClip(
        word='test',
        video_code='1aphO1Zd2kg',
        start_time=123.99,
        end_time=124.2,
        logger='a.txt'
    )

#    clip.transcribe()
#    clip.play()

    slow_clip = clip.change_speed(0.6)
#    slow_clip.play()
    new_clip = clip.crop((1.2, 5))
    slow_clip.get_matching_video()

#    clip.play()
