import argparse
import os
import csv
from subprocess import check_output
from youtube_utils import download_video, video_to_flac, upload_blob, change_video_speed, seconds_to_timecode
from speech_to_text import sample_recognize
from shutil import copyfile

LOG_DIRECTORY = './logs'
VOCAB_DIRECTORY = './vocabulary'
TRUSTED_VOCABULARY_DIRECTORY = './trusted-vocabulary'
MEDIA_DIRECTORY = './media'
AUDIO_SUBDIRECTORY = 'audio'
VIDEO_SUBDIRECTORY = 'video'
GOOD_CLIPS_SUBDIRECTORY = 'words'

clean_word = lambda x: ''.join([c for c in x.lower() if c.isalpha() or c.isdigit() or c==' ']).rstrip()

def get_word_time(word, audio_filepath, must_isolate=False, min_confidence=0.7, log_filepath=''):
    # TODO: Allow for close matches e.g. Hillbillies to hill billies
    # Use GCP Speech-to-Text to refine clip cropping
    found_word = False
    start_time = 0
    end_time = 0
    confidence = 0
    try:
        text = sample_recognize(audio_filepath, log_filepath)
    except IndexError:
        raise FileNotFoundError("GCP didn't detect the word in our clip. Exiting...")

    for w in text.words:
        if clean_word(w.word) == word:
            found_word = True
            start_time = float(str(w.start_time.seconds) + '.' + str(w.start_time.nanos))
            end_time = float(str(w.end_time.seconds) + '.' + str(w.end_time.nanos))
            confidence = float(w.confidence)

            if must_isolate and len(text.words) > 1:
                raise FileExistsError("GCP detected our word but not isolated.")

    if not found_word or confidence < min_confidence:
        raise FileNotFoundError("GCP didn't detect the word in our clip. Exiting...")

    return start_time, end_time, confidence


def get_clip_information(word):
    tsv_filepath = vocabulary_filepath(word)
    clip_info_list = []
    with open(tsv_filepath, mode='r') as infile:
        reader = csv.reader(infile, delimiter='\t')
        next(reader)
        for row in reader:
            clip_info_list += [(row[0], float(row[1]), float(row[2]))]
    return clip_info_list


def erase_tsv_row(word, selection_function):
    # Read all into memory
    tsv_filepath = vocabulary_filepath(word)
    clip_info_list = []
    with open(tsv_filepath, mode='r') as infile:
        reader = csv.reader(infile, delimiter='\t')
        next(reader)
        for row in reader:
            clip_info_list += [(row[0], float(row[1]), float(row[2]))]

    dont_write = selection_function(clip_info_list)
    clip_info_list = [x for x in clip_info_list if x != dont_write]

    # Delete TSV
    os.remove(tsv_filepath)

    # Quit here if no clips are left
    if clip_info_list == []:
        return

    with open(tsv_filepath, mode='a') as out:
        writer = csv.writer(out, delimiter='\t', lineterminator='\n')
        writer.writerow(['video_code', 'start_time', 'end_time'])
        for row in clip_info_list:
            writer.writerow(row)


def vocabulary_filepath(word):
    vocab_subdirectory = word[0].upper()
    filepath = f'{VOCAB_DIRECTORY}/{vocab_subdirectory}/{word}.tsv'
    return filepath


def next_clean_log_file(safe_word):
    log_subdirectory = f'{LOG_DIRECTORY}/{safe_word}'
    if not os.path.exists(log_subdirectory):
        os.makedirs(log_subdirectory)

    index = 0
    LOG_FILEPATH = f'{log_subdirectory}/{safe_word}-{index}.txt'
    while os.path.exists(LOG_FILEPATH):
        index += 1
        LOG_FILEPATH = f'{log_subdirectory}/{safe_word}-{index}.txt'
    return LOG_FILEPATH


def trusted_load(safe_word, tsv_filepath):
    LOG_FILEPATH = next_clean_log_file(safe_word)

    clip_info_list = []
    with open(tsv_filepath, mode='r') as infile:
        reader = csv.reader(infile, delimiter='\t')
        next(reader)
        for row in reader:
            clip_info_list += [(
                row[0],
                float(row[1]),
                float(row[2]),
                float(row[3]),
                float(row[4]),
                float(row[5]),
            )]
    clip_info = clip_info_list[0]
    video_code, clip_start_time, clip_end_time, speed_multiplier, word_start_time, word_end_time = clip_info

    clip_filepath = f'{MEDIA_DIRECTORY}/{VIDEO_SUBDIRECTORY}/raw-clips/{safe_word}/{safe_word}.mkv'
    safety_buffer = 1
    download_video(video_code, clip_start_time, clip_end_time, clip_filepath, safety_buffer=safety_buffer, log_filepath=LOG_FILEPATH)

    slow_clip_filepath = f'{MEDIA_DIRECTORY}/{VIDEO_SUBDIRECTORY}/slow-clips/{safe_word}-{int(speed_multiplier*100)}-percent.mkv'
    change_video_speed(clip_filepath, 0.7, slow_clip_filepath, LOG_FILEPATH)

    slow_word_modified_filepath = f'video/slow-word-clips/{safe_word}.mkv'
    cropping_command = f'ffmpeg -y -ss 0 -i {slow_clip_filepath} -ss {word_start_time} -t {word_end_time - word_start_time} -c:v libx264 -c:a aac {slow_word_modified_filepath}'
    with open(LOG_FILEPATH, 'a') as log:
        check_output(cropping_command, shell=True, stderr=log)

    final_filepath = f'video/best-clips/{safe_word}.mkv'
    copyfile(slow_word_modified_filepath, final_filepath)

    return final_filepath




def clip_word(word):
    '''
    Algorithm
        Clean word (to avoid errors from bad strings & directories)

        (1) Locate clip information
            If word not in caption vocabulary, throw error
            Select row one instance of word from vocabulary/[first letter of word]/[word].tsv
        (2) Download & trim clip
            Download row one clip with spare leading and trailing time (approx 1 second)
            Convert to FLAC
            Use GCP Speech-to-text API to find accurate word start and end time
            Trim downloaded clip to just the word
        (3) Check quality
            Convert new clip to FLAC
            Use GCP to transcribe clip
            If transcription is not just our word, remove row one of TSV & return to (1)
    '''

    # TODO
    # Stop re-downloading elements if they exist locally
    # Also delete videos or move to an archive if they are failures

    # Clean word
    safe_word = clean_word(word)

    # Check if we have a trusted clip source to use
    vocab_subdirectory = word[0].upper()
    filepath = f'./trusted-vocabulary/{vocab_subdirectory}/{safe_word}.tsv'
    if os.path.exists(filepath):
        print(f'Performing trusted load on {safe_word}')
        return trusted_load(safe_word, filepath)


    word_retrieved = False
    while not word_retrieved:
        LOG_FILEPATH = next_clean_log_file(safe_word)
        generated_clips_info = {}

        # If word not in vocabulary, throw error
        print(f'Checking if "{safe_word}" is in vocabulary...')
        filepath = vocabulary_filepath(safe_word)
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"We don't have the word {safe_word} yet!")

        # Get information on all clips of the word
        print(f'Getting information on all instances of "{safe_word}"')
        clip_info_list = get_clip_information(safe_word)
        print(f'The vocabulary holds {len(clip_info_list)} instances of "{safe_word}"')

        # Pick clip to use
        def max_clip_length_function(clip_info_list):
            clip_info_list = [(x[2]-x[1], x) for x in clip_info_list]
            return max(clip_info_list)[1]

        clip_info = max_clip_length_function(clip_info_list)
        video_code, raw_clip_start_time, raw_clip_end_time = clip_info

        # Download a clip which includes the word, plus some time on both sides
        print(f'Clip selected. VC={video_code}, start={seconds_to_timecode(raw_clip_start_time)}, '+\
              f'end={seconds_to_timecode(raw_clip_end_time)}.\n' +\
              f'Link: https://www.youtube.com/watch?v={video_code}')

        # Find next clear raw clip filepath
        raw_clip_dir = f'{MEDIA_DIRECTORY}/{VIDEO_SUBDIRECTORY}/{safe_word}/raw-clips'
        if not os.path.exists(raw_clip_dir):
            os.makedirs(raw_clip_dir)
        index = 0
        raw_clip_filepath = f'{raw_clip_dir}/{safe_word}-{index}.mkv'
        while os.path.exists(raw_clip_filepath):
            index += 1
            raw_clip_filepath = f'{raw_clip_dir}/{safe_word}-{index}.mkv'


        # TODO: If you start to close to the beginning of a video, we fail for lookahead
        safety_buffer = 1
        download_video(video_code, raw_clip_start_time, raw_clip_end_time, raw_clip_filepath, safety_buffer=safety_buffer, log_filepath=LOG_FILEPATH)
        clip_length = raw_clip_end_time - raw_clip_start_time + 2*safety_buffer
        print(f'Raw clip of length {round(clip_length, 2)} seconds saved to {raw_clip_filepath}')

        # Now we slow it down (this seems to improve recognition)
        speed_multiplier = 0.7
        print(f'Slowing clip by factor of {speed_multiplier}')
        slow_clips_subdirectory = f'{MEDIA_DIRECTORY}/{VIDEO_SUBDIRECTORY}/{safe_word}/slow-clips'
        if not os.path.exists(slow_clips_subdirectory):
            os.makedirs(slow_clips_subdirectory)
        slow_clip_filepath = f'{slow_clips_subdirectory}/{safe_word}-{index}-{int(speed_multiplier*100)}-percent.mkv'

        change_video_speed(raw_clip_filepath, 0.7, slow_clip_filepath, LOG_FILEPATH)
        print(f'Slowed clip of length {round(clip_length * (1/speed_multiplier), 2)} seconds saved to {slow_clip_filepath}')

        # Convert to audio
        print(f'Converting clip {slow_clip_filepath} to mono FLAC audio...')
        slow_clips_audio_subdirectory = f'{MEDIA_DIRECTORY}/{AUDIO_SUBDIRECTORY}/{safe_word}/slow-clips'
        if not os.path.exists(slow_clips_audio_subdirectory):
            os.makedirs(slow_clips_audio_subdirectory)
        mono_filepath = f'{slow_clips_audio_subdirectory}/{safe_word}-{index}.flac'
        video_to_flac(slow_clip_filepath, mono_filepath, LOG_FILEPATH)
        print(f'Audio saved to {mono_filepath}')

        # Get start and end time for word in slowed clip
        print(f'Querying GCPs Speech-to-Text API with audio clip {mono_filepath}')
        try:
            word_start_time, word_end_time, conf = get_word_time(safe_word, mono_filepath, min_confidence=0.85, log_filepath=LOG_FILEPATH)
        except FileNotFoundError:
            print(f'Word "{safe_word}" not found in audio clip {mono_filepath}')
            print(f'Entry deemed bad -- erasing clip info from {safe_word} TSV...')
            erase_tsv_row(safe_word, max_clip_length_function)
            continue

        print(f'Word "{safe_word}" found at interval ({word_start_time}, {word_end_time}) with confidence {round(conf, 2)}/1.0')

        #TODO: Add changes to beginning time
        print(f'Beginning crop trials to find best interval for word...')
        # We trim, ask GCP if right. If wrong, trim in more until start === end
        conf_list = []
        increment = 0.08 # Arbitrarily chosen
        steps = 20
        alterations = [(0, (s*increment)-(steps//2)*increment) for s in range(steps)]

        for i, (beginning_alteration, end_alteration) in enumerate(alterations):
            # For each new alteration, we create a clip
            word_start_time = word_start_time + beginning_alteration
            shifted_word_end_time = word_end_time + end_alteration

            cropped_audio_directory = f'{MEDIA_DIRECTORY}/{AUDIO_SUBDIRECTORY}/{safe_word}/cropped'
            if not os.path.exists(cropped_audio_directory):
                os.makedirs(cropped_audio_directory)
            slow_word_modified_filepath = f'{cropped_audio_directory}/{safe_word}-{index}-{i}.flac'

            # Retrim
            clip_length = shifted_word_end_time - word_start_time
            with open(LOG_FILEPATH, 'a') as log:
                if clip_length > 0.1:
                    print(f'Cropping {mono_filepath} to interval ({word_start_time}, {shifted_word_end_time}) and writing to {slow_word_modified_filepath}')
                    log.write(f'Cropping slowed approximate clip to interval ({word_start_time}, {shifted_word_end_time})\n')
                    log.write(f'Cropped clip to be written to {slow_word_modified_filepath}\n')
                    cropping_command = f'ffmpeg -y -ss 0 -i {mono_filepath} -ss {word_start_time} -t {round(shifted_word_end_time - word_start_time, 4)} -c:a flac {slow_word_modified_filepath}'
                    log.write(f'Executing: {cropping_command}\n')
                    check_output(cropping_command, shell=True, stderr=log)

                    # TODO: Complete this to make easier re-lookups
                    generated_clips_info[slow_word_modified_filepath] = {
                        'video_code': video_code,
                        'clip_start_time': raw_clip_start_time,
                        'clip_end_time': raw_clip_end_time,
                        'speed_multiplier': speed_multiplier,
                        'start_time': word_start_time,
                        'end_time': shifted_word_end_time
                    }

                else:
                    print(f'Proposed crop interval ({word_start_time}, {shifted_word_end_time}) was deemed too short. Skipping...')
                    log.write(f'Proposed clip crop interval ({word_start_time}, {shifted_word_end_time}) was deemed too short. Skipping...\n')
        print(f'All word crops generated.')


        conf_list = []
        for i in range(steps):
            cropped_mono_filepath = f'{MEDIA_DIRECTORY}/{AUDIO_SUBDIRECTORY}/{safe_word}/cropped/{safe_word}-{index}-{i}.flac'
            if not os.path.exists(cropped_mono_filepath):
                continue

            print(f'Querying GCPs Speech-to-Text API with audio clip {cropped_mono_filepath}')
            try:
                trim_start_time, trim_end_time, conf = get_word_time(safe_word, cropped_mono_filepath, must_isolate=True, min_confidence=0.85, log_filepath=LOG_FILEPATH)
                print(f'Word "{safe_word}" found at interval ({trim_start_time}, {trim_end_time}) with {round(conf, 2)}/1.0 confidence')
                conf_list += [(i, conf)]
            except FileNotFoundError:
                print(f'Word "{safe_word}" not found in audio clip {cropped_mono_filepath}')
            except FileExistsError:
                print(f'Word "{safe_word}" was found in audio clip {cropped_mono_filepath}, but not isolated')

        print(conf_list)

        if conf_list != []:
            print(f'Word "{safe_word}" found in audio clips {[i for i, conf in conf_list]}')
            clip_num, conf = max(conf_list, key=lambda x: float(x[1]))
            cropped_mono_filepath = f'{MEDIA_DIRECTORY}/{AUDIO_SUBDIRECTORY}/{safe_word}/cropped/{safe_word}-{index}-{clip_num}.flac'

            print(f'Maximum confidence of {round(conf, 2)} came from clip {cropped_mono_filepath}')
            word_retrieved = True

#            print(f'Writing trusted clip info to trusted vocabulary')
            best_clip_info = generated_clips_info[cropped_mono_filepath]
#            add_to_trusted_vocabulary(safe_word, best_clip_info)

            # Generate a video clip to match the best audio
            final_filepath = f'{MEDIA_DIRECTORY}/{GOOD_CLIPS_SUBDIRECTORY}/{safe_word}-{round(conf, 2)}.mkv'
            cropping_command = f'ffmpeg -y -ss 0 -i {slow_clip_filepath} -ss {best_clip_info["start_time"]} -t {round(best_clip_info["end_time"] - best_clip_info["start_time"], 4)} -c:v libx264 -c:a flac {final_filepath}'
            print('Executing: ', cropping_command)
            with open(LOG_FILEPATH) as log:
                check_output(cropping_command, shell=True, stderr=log)
            return final_filepath

        else:
            print(f'No audio clip contained word "{safe_word}"')
            print(f'Entry deemed bad -- erasing clip info from {safe_word} TSV...')
            erase_tsv_row(safe_word, max_clip_length_function)

    return word_clip_filepath



def write_to_tsv(row, header, filepath):
    mode = 'w'
    if os.path.exists(filepath):
        mode = 'a'

    with open(filepath, mode) as f:
        writer = csv.writer(f, delimiter='\t', lineterminator='\n')
        if mode == 'w':
            writer.writerow(header)
        writer.writerow(row)



def add_to_trusted_vocabulary(safe_word, clip_info):
    vocabulary_directory = './trusted-vocabulary'
    vocab_subdirectory = safe_word[0].upper()

    dir_path = f'{vocabulary_directory}/{vocab_subdirectory}'
    filepath = f'{dir_path}/{safe_word}.tsv'
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    video_code = clip_info['video_code']
    clip_start_time = clip_info['clip_start_time']
    clip_end_time = clip_info['clip_end_time']
    speed_multiplier = clip_info['speed_multiplier']
    word_start_time = clip_info['start_time']
    word_end_time = clip_info['end_time']

    write_to_tsv(
        [video_code, clip_start_time, clip_end_time, speed_multiplier, word_start_time, word_end_time],
        'video_code clip_start_time clip_end_time speed_multiplier word_start_time word_end_time'.split(),
        filepath
    )




if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('word')
    args = parser.parse_args()

    clip_word(str(args.word))
