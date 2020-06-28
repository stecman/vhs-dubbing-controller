import os
import datetime
import glob

class FileManager:
    _instance = None

    @staticmethod
    def instance():
        if FileManager.__instance is None:
            raise Exception("No instance set. Pass a FileManager instance to set_instance()")

        return FileManager.__instance

    @staticmethod
    def set_instance(recorder):
        FileManager.__instance = recorder

    def __init__(self, storage_path, db_file):
        self.storage_path = storage_path
        self.db_file = db_file

        self.tape_number = self._read_tape_num_from_file()

    def get_state(self):
        return {
            "tape_number": '%03d' % self.tape_number,
            "recording_count": self._count_recordings()
        }

    def increment_tape_number(self):
        self.tape_number += 1
        self._write_count(self.tape_number, self.db_file)

    def save_note(self, text):
        tape_dirname = self._get_tape_dirname()
        output_path = os.path.join(self.storage_path, tape_dirname)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(output_path, "%s_capture_%s.txt" % (tape_dirname, timestamp))

        # Ensure the directory exists to write to
        os.makedirs(output_path, exist_ok=True)

        # Write note to file
        with open(output_file, 'a') as note_handle:
            note_handle.write(text)

    def new_recording_path(self):
        tape_dirname = self._get_tape_dirname()
        output_path = os.path.join(self.storage_path, tape_dirname)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(output_path, "%s_capture_%s.mkv" % (tape_dirname, timestamp))

        # Ensure the directory exists to write to
        os.makedirs(output_path, exist_ok=True)

        # Sanity check the output path
        if os.path.exists(output_file):
            raise Exception("ERROR: File %s exists. Refusing to overwrite" % output_file)

        return output_file

    def _count_recordings(self):
        output_dir = os.path.join(self.storage_path, self._get_tape_dirname())

        if os.path.isdir(output_dir):
            return len(glob.glob(os.path.join(output_dir, '*.mkv')))
        else:
            return 0

    def _get_tape_dirname(self):
        return "vhs_tape_%03d" % self.tape_number

    def _read_tape_num_from_file(self):
        # Create the file if it doesn't exist
        if not os.path.exists(self.db_file):
            self._write_count(1, self.db_file)

        with open(self.db_file, 'r') as handle:
            try:
                return int(handle.read().strip())
            except:
                return 1

    def _write_count(self, value, filename):
        with open(self.db_file, 'w') as handle:
            handle.write(str(value))