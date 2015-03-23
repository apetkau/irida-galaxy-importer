import logging
import sys
from bioblend.galaxy.objects import GalaxyInstance
from bioblend import galaxy
import json
from sample import Sample
from sample_file import SampleFile
import optparse
import os.path
from requests_oauthlib import OAuth2Session

# FOR DEVELOPMENT ONLY!!
# This value only exists for this process and processes that fork from it (none)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'


class IridaImport:

    """
    Imports sample's sample files from IRIDA.

    An appropriate library and folders are created if necessary
    """

    ADMIN_KEY = "09008eb345c9d5a166b0d8f301b1e72c"
    GALAXY_URL = "http://localhost:8888/"
    ILLUMINA_PATH = '/illumina_reads'
    REFERENCE_PATH = '/references'

    CLIENT_ID = 'webClient'  # This value must also be set in irida_import.xml
    CLIENT_SECRET = 'webClientSecret'

    TOKEN_ENDPOINT = 'http://localhost:8080/api/oauth/token'

    def get_samples(self, samples_dict):
        """
        Create sample objects from a dictionary.

        :type json_params_dict: dict
        :param json_params__dict: a dictionary to parse. See one of the test
        json files for formating information (the format will likely
        change soon)
        :return: a list of output samples
        """
        samples = []
        for sample_input in samples_dict:
            sample_name = sample_input['name']
            sample_path = sample_input['_links']['self']['href']

            sample = Sample(sample_name, sample_path)

            for sample_file_input in sample_input['_embedded']['sample_files']:
                sample_file_url = sample_file_input['_links']['self']['href']

                sample_file = self.get_sample_file(sample_file_url)
                sample.sample_files.append(sample_file)

            samples.append(sample)
        return samples

    def get_sample_file(self, sample_file_url):
        """
        From an IRIDA REST API URL, get a sample file
        :type str
        :param sample_file_url: the URL to get the sample file representation
        :return: a sample file with a name and path
        """
        response = self.irida.get(sample_file_url)
        resource = response.json()['resource']
        logging.debug("The JSON parameters from the IRIDA API are:\n" +
                      json.dumps(resource, indent=2))

        name = resource['fileName']
        path = resource['file']

        return SampleFile(name, path)

    def get_first_or_make_lib(self, desired_lib_name, email):
        """"
        Get or if neccessary create a library that matches a given name.

        :type desired_lib_name: str
        :param desired_lib_name: the desired library name
        :type email: str
        :param email: the email of the Galaxy user to get or make a library for
        :rtype: :class:`~.LibraryDataset`
        :return: the obtained or created library

        This method should never make a library with the same name as an already
        existing library that is accessible using the administrator API key

        """
        lib = None
        libs = self.gi.libraries.list(name=desired_lib_name)
        if len(libs) > 0:
            lib = next(lib_i for lib_i in libs if lib_i.deleted is False)

        if(lib is None):
            users = self.reg_gi.users.get_users()
            uid = 0
            try:
                uid = next(user['id']
                           for user in users if user['email'] == email)
            except StopIteration:
                error = "No Galaxy user could be found for the email: '{0}', "\
                    "quiting".format(email)
                logging.exception(error)
                self.print_summary()
                sys.stderr.write(error)
                sys.exit(1)

            lib = self.gi.libraries.create(desired_lib_name)
            self.reg_gi.libraries.set_library_permissions(
                lib.id, access_in=[uid], modify_in=[uid], add_in=[uid])
        return lib

    def create_folder_if_nec(self, folder_path):
        """
        Add a folder to a library, if it does not already exist.

        :type folder_path: str
        :param folder_patht: The folder's path e.g. '/bobfolder/bobfolder2'
        """
        made_folder = None
        # Get the folder name from the path, e.g. 'bobfolder2' from
        # '/bobfolder/bobfolder2'
        folder_name = folder_path.rsplit("/", 1)[1]
        # Get the base folder path from the path e.g '/bobfolder' from
        # '/bobfolder/bobfolder2'
        base_folder_path = folder_path.rsplit("/", 1)[0]
        logging.debug(
            'If neccessary, making a folder named \'%s\' on base folder path'
            '\'%s\' from folder path \'%s\'' %
            (folder_name, base_folder_path, folder_path))

        if not self.exists_in_lib('folder', 'name', folder_path):

            base_folder_list = self.reg_gi.libraries.get_folders(
                self.library.id,
                name=base_folder_path)

            if len(base_folder_list) > 0:
                base_folder = self.library.get_folder(base_folder_list[0]['id'])
                made_folder = self.library.create_folder(
                    folder_name,
                    base_folder=base_folder)
            elif base_folder_path == '':
                made_folder = self.library.create_folder(folder_name)
            else:
                raise IOError('base_folder_path must include an existing base'
                              'folder, or nothing')
            logging.debug('Made folder with path:' + '\'%s\'' % folder_path)
        return made_folder

    def exists_in_lib(self, item_type, item_attr_name, desired_attr_value):
        """
        Find if an item of given type and attribute exists in the library

        :type item_type: str
        :param item_type: the item type e.g "folder" or "file"
        :type item_attr_name: str
        :param item_attr_name: the item attribute e.g "name"
        :type desired_attr_value: str
        :param desired_attr_value: the desired attribute value e.g "Bob"

        :rtype: Boolean
        :return: whether the item exists in the library
        """
        ans = False
        # check for an object of the desired type with the desired attribute
        self.library = self.gi.libraries.get(self.library.id)
        for con_inf in self.library.content_infos:
            if con_inf.type == item_type:
                attr = getattr(con_inf, item_attr_name)
                if attr == desired_attr_value:
                    ans = True
                    break
        return ans

    def unique_file(self, sample_file_path, galaxy_name):
        """
        Find out if a sample file is unique

        :type sample_file_path: str
        :param sample_file_path: the local file path to the file to check
        :type galaxy_name: str
        :param galaxy_name: the full path to the sample file as it would
        exist in Galaxy
        :rtype: Boolean
        :return: whether a file with this name and size does not exist in Galaxy
        """
        logging.debug(
            "Doing a basic check for already existing sample file at: " +
            galaxy_name)
        unique = True
        size = os.path.getsize(sample_file_path)
        self.library = self.gi.libraries.get(self.library.id)
        datasets = self.library.get_datasets(name=galaxy_name)
        for dataset in datasets:
            # Galaxy sometimes appends a newline
            if(dataset.file_size in (size, size + 1)):
                unique = False
                break
        return unique

    def add_sample_if_nec(self, sample):
        """
        Upload a sample's sample files if they are not already present in Galaxy

        :type sample: Sample
        :param sample: the sample to upload
        """
        added_to_galaxy = []
        for sample_file in sample.sample_files:
            sample_folder_path = self.ILLUMINA_PATH+'/'+sample.name
            galaxy_sample_file_name = sample_folder_path+'/'+sample_file.name

            if os.path.isfile(sample_file.path):
                if self.unique_file(sample_file.path, galaxy_sample_file_name):
                    logging.debug(
                        "  Sample file does not exist so uploading/linking it")
                    added = self.link(
                        sample_file, sample_folder_path)
                    if(added):
                        added_to_galaxy.extend(added)
                        self.uploaded_files_log.append(
                            {'local_path': sample_file.path,
                             'galaxy_name': galaxy_sample_file_name})
                        logging.info('Exported: ' + galaxy_sample_file_name)
                else:
                    self.skipped_files_log.append(
                        {'local_path': sample_file.path,
                         'galaxy_name': galaxy_sample_file_name})
                    logging.warning(
                        'Skipped exporting: ' +
                        galaxy_sample_file_name)
            else:
                self.unfound_files_log.append({'local_path': sample_file.path})
                logging.error('file not found: '+sample_file.path)
        return added_to_galaxy

    def link(self, sample_file, sample_folder_path):
        """
        Add a sample file to Galaxy, linking to it locally

        :type sample_file: SampleFile
        :param sample_file: the sample file to link
        :type sample_folder_path: str
        :param sample_folder_path: the folder in Galaxy to store the file in
        :return: a list containing a single dict with the file's
        url, id, and name.
        """
        logging.debug('      Attempting to upload a file')
        added = None
        file_path = sample_file.path
        logging.debug(
            "       Sample file's local path is" + file_path)

        folder_id = self.reg_gi.libraries.get_folders(
            self.library.id, name=sample_folder_path)[0]['id']
        added = self.reg_gi.libraries.upload_from_galaxy_filesystem(
            self.library.id,
            file_path,
            folder_id=folder_id,
            link_data_only='link_to_files')
        return added

    def print_summary(self):
        """
        Print a final summary of the tool's activity
        """
        logging.warn('\nFinal summary:')
        logging.info('{0} file(s) exported and {1} file(s) skipped.'
                     .format(len(self.uploaded_files_log),
                             len(self.skipped_files_log)))
        self.print_files_log('\nFiles exported:', self.uploaded_files_log)
        self.print_files_log(
            "\nSome files couldn't be exported because they don't exist:",
            self.unfound_files_log)
        self.print_files_log(
            '\nSome files were skipped because they were not unique:',
            self.skipped_files_log)

    def print_files_log(self, message, log):
        """
        Print a log file dictionary with a preceding message
        :type message: str
        :param message: A message to show before the files are listed
        :type log: dict
        :param log: The local file path and galaxy name of the file
        """
        if log:
            logging.warn(message)
            for file_log in log:
                logging.warn('File with local path: {0}\n and Galaxy path: {1}'
                             .format(file_log['local_path'],
                                     file_log['galaxy_name']))

    def get_IRIDA_session(self, oauth_dict):
        """
        Create an OAuth2 session with IRIDA

        :type oauth_dict dict
        :param oauth_dict: configuration information
        """
        redirect_uri = oauth_dict['redirect']
        auth_code = oauth_dict['code']
        if self.token:
            irida = OAuth2Session(client_id=self.CLIENT_ID,
                                  redirect_uri=redirect_uri,
                                  token={'access_token': self.token})
        else:
            irida = OAuth2Session(self.CLIENT_ID, redirect_uri=redirect_uri)
            irida.fetch_token(
                self.TOKEN_ENDPOINT, client_secret=self.CLIENT_SECRET,
                authorization_response=redirect_uri + '?code=' + auth_code)
        return irida

    def import_to_galaxy(self, json_parameter_file, config, token):
        """
        Import samples and their sample files into Galaxy from IRIDA

        :type json_parameter_file: str
        :param json_parameter_file: a path that Galaxy passes,
        to the stub datasource it created
        :type config: str
        :param config: a local JSON file containing configuration info.
        It is currently unused
        :type token: str
        :param token: An access token that can be passed to the tool when it
        is manually run.
        """
        with open(json_parameter_file, 'r') as param_file_handle:
            full_param_dict = json.loads(param_file_handle.read())
            param_dict = full_param_dict['param_dict']
            json_params_dict = json.loads(param_dict['json_params'])
            logging.info("Exporting files from IRIDA to Galaxy:\n")
            logging.debug("The full Galaxy param dict is: " +
                          json.dumps(full_param_dict, indent=2))
            logging.debug("The JSON parameters from IRIDA are:\n" +
                          json.dumps(json_params_dict, indent=2))
            self.uploaded_files_log = []
            self.skipped_files_log = []
            self.unfound_files_log = []
            samples_dict = json_params_dict['_embedded']['samples']
            email = json_params_dict['_embedded']['user']['email']
            desired_lib_name = json_params_dict['_embedded']['library']['name']
            oauth_dict = json_params_dict['_embedded']['oauth2']
            self.token = token
            self.irida = self.get_IRIDA_session(oauth_dict)

            self.gi = GalaxyInstance(self.GALAXY_URL, self.ADMIN_KEY)

            # This is necessary for uploads from arbitary local paths
            # that require setting the "link_to_files" flag:
            self.reg_gi = galaxy.GalaxyInstance(
                url=self.GALAXY_URL,
                key=self.ADMIN_KEY)

            # Each sample contains a list of sample files
            samples = self.get_samples(samples_dict)

            # Set up the library
            self.library = self.get_first_or_make_lib(desired_lib_name, email)
            self.create_folder_if_nec(self.ILLUMINA_PATH)
            self.create_folder_if_nec(self.REFERENCE_PATH)

            # Add each sample's files to the library
            for sample in samples:
                logging.debug("sample name is" + sample.name)
                self.create_folder_if_nec(self.ILLUMINA_PATH+'/'+sample.name)
                self.add_sample_if_nec(sample)

            self.print_summary()

"""
From the command line, pass JSON files to IridaImport, and set up the logger
"""
if __name__ == '__main__':
    # TODO: convert to robustly use argparse
    logging.basicConfig(filename="log_irida_import", level=logging.DEBUG,
                        filemode="w")
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    logger = logging.getLogger()
    logger.addHandler(stream_handler)

    # Prevent urllib3 from spamming stdout
    urllib3_logger = logging.getLogger('requests.packages.urllib3')
    urllib3_logger.setLevel(logging.WARNING)

    logging.debug("Parsing the Command Line")
    parser = optparse.OptionParser()
    parser.add_option(
        '-p', '--json_parameter_file', dest='json_parameter_file',
        action='store', type="string",
        help='A JSON formatted parameter file from Galaxy')
    parser.add_option(
        '-s', '--config', dest='config',
        action='store', type="string",
        help='A configuration file will go here')
    parser.add_option(
        '-t', '--token', dest='token',
        action='store', type='string',
        help='The tool can use a supplied access token' +
        'instead of querying IRIDA')

    (options, args) = parser.parse_args()

    # this test JSON file does not have to be configured to run the tests
    logging.debug("Opening a test json file")
    test_json_file = \
        '/home/jthiessen/galaxy-dist/tools/irida_import_tool_for_galaxy/irida_import/sample.dat'

    importer = IridaImport()

    if options.config is None:
        logging.debug("No passed file so reading local file")
        importer.import_to_galaxy(test_json_file, None, options.token)
    else:
        logging.debug("Reading from passed file")
        importer.import_to_galaxy(
            options.json_parameter_file,
            None,
            options.token)
