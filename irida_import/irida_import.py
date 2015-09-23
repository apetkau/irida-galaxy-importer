import time
import logging
import argparse
import json
import os.path
import ConfigParser
import shutil
import sys
from xml.etree import ElementTree

from bioblend.galaxy.objects import GalaxyInstance
from bioblend import galaxy
from requests_oauthlib import OAuth2Session

from sample import Sample
from sample_file import SampleFile


# FOR DEVELOPMENT ONLY!!
# This value only exists for this process and processes that fork from it (none)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Print the token so that it can be used to call the tool from the command line
PRINT_TOKEN_INSECURELY = False


class IridaImport:

    """
    Imports sample's sample files from IRIDA.

    An appropriate library and folders are created if necessary
    """

    CONFIG_FILE = 'config.ini'
    XML_FILE_SAMPLE = 'irida_import.xml.sample'
    XML_FILE = 'irida_import.xml'
    CLIENT_ID_PARAM = 'galaxyClientID'

    def __init__(self):
        self.logger = logging.getLogger('irida_import')

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

        # Raise an exception if we get 4XX or 5XX server response
        response.raise_for_status()

        resource = response.json()['resource']
        self.logger.debug("The JSON parameters from the IRIDA API are:\n" +
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
            roles = self.reg_gi.roles.get_roles()
            rid = 0
            try:
                rid = next(role['id']
                           for role in roles if role['name'] == email)
            except StopIteration:
                error = "No Galaxy role could be found for the email: '{0}', "\
                    "quiting".format(email)
                raise Exception(error)

            lib = self.gi.libraries.create(desired_lib_name)
            self.reg_gi.libraries.set_library_permissions(
                lib.id, access_in=[rid], modify_in=[rid], add_in=[rid])
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
        self.logger.debug(
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
            self.logger.debug('Made folder with path:' + '\'%s\'' % folder_path)
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
        self.logger.debug(
            "Doing a basic check for already existing sample file at: " +
            galaxy_name)
        unique = True
        size = os.path.getsize(sample_file_path)
        self.library = self.gi.libraries.get(self.library.id)
        datasets = self.library.get_datasets(name=galaxy_name)
        for dataset in datasets:
            # Galaxy sometimes appends a newline, see:
            # https://bitbucket.org/galaxy/galaxy-dist/src/7e4d21621ce12e13ebbdf9fd3259df58c3ef124c/lib/galaxy/datatypes/data.py?at=stable#cl-673
            if dataset.file_size in (size, size + 1):
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
                    self.logger.debug(
                        "  Sample file does not exist so uploading/linking it")
                    added = self.link(
                        sample_file, sample_folder_path)
                    if(added):
                        added_to_galaxy.extend(added)
                        self.print_logged(time.strftime("[%D %H:%M:%S]:") +
                                          ' Imported file with Galaxy path: ' +
                                          galaxy_sample_file_name)
                        self.uploaded_files_log.append(
                            {'galaxy_name': galaxy_sample_file_name})
                else:
                    self.print_logged(time.strftime("[%D %H:%M:%S]:") +
                                      ' Skipped file with Galaxy path: ' +
                                      galaxy_sample_file_name)
                    self.skipped_files_log.append(
                        {'galaxy_name': galaxy_sample_file_name})
            else:
                error = ("File not found:\n Galaxy path:{0}\nLocal path:{1}"
                         ).format(galaxy_sample_file_name, sample_file.path)
                raise ValueError(error)
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
        self.logger.debug('      Attempting to upload a file')
        added = None
        file_path = sample_file.path
        self.logger.debug(
            "       Sample file's local path is" + file_path)
        file_type = 'auto'
        # Assume fastq files are fastqsanger:
        if os.path.splitext(file_path)[1] == '.fastq':
            file_type = 'fastqsanger'

        folder_id = self.reg_gi.libraries.get_folders(
            self.library.id, name=sample_folder_path)[0]['id']
        added = self.reg_gi.libraries.upload_from_galaxy_filesystem(
            self.library.id,
            file_path,
            folder_id=folder_id,
            link_data_only='link_to_files',
            file_type=file_type
        )
        return added

    def print_summary(self, failed=False):
        """
        Print a final summary of the tool's activity
        """
        def print_files_log(message, log):
            """For the summary, print a log's file's details"""
            if log:
                self.print_logged(message)
                for file_log in log:
                    self.print_logged('File with Galaxy path: {0}'
                                      .format(file_log['galaxy_name']))

        if failed:
            self.print_logged('Import failed.')
        else:
            self.print_logged('Import completed successfully.')
        self.print_logged('Final summary:\n'
                          '{0} file(s) imported and {1} file(s) skipped.'
                          .format(len(self.uploaded_files_log),
                                  len(self.skipped_files_log)))
        print_files_log(
            '\nSome files were skipped because they were not unique:',
            self.skipped_files_log)

    def print_logged(self, message):
        """Print a message and log it"""
        self.logger.info(message)
        print message

    def get_IRIDA_session(self, oauth_dict):
        """
        Create an OAuth2 session with IRIDA

        :type oauth_dict: dict
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
        if PRINT_TOKEN_INSECURELY:
            self.print_logged(irida.token)
        return irida

    def configure(self):
        """
        Configure the tool using the configuration file

        The
        """
        this_module_path = os.path.abspath(__file__)
        parent_folder = os.path.dirname(this_module_path)
        src = os.path.join(parent_folder, self.XML_FILE_SAMPLE)
        dest = os.path.join(parent_folder, self.XML_FILE)
        # Allows storing recommended configuration options in a sample XML file
        # and not commiting the XML file that Galaxy will read:
        try:
            shutil.copyfile(src, dest)
        except:
            pass

        config_path = os.path.join(parent_folder, self.CONFIG_FILE)
        with open(config_path, 'r') as config_file:
            config = ConfigParser.ConfigParser()
            config.readfp(config_file)

            # TODO: parse options from command line and config file as a list
            self.ADMIN_KEY = config.get('Galaxy', 'admin_key')
            self.GALAXY_URL = config.get('Galaxy', 'galaxy_url')
            self.ILLUMINA_PATH = config.get('Galaxy', 'illumina_path')
            self.REFERENCE_PATH = config.get('Galaxy', 'reference_path')
            self.XML_FILE = config.get('Galaxy', 'xml_file')

            self.TOKEN_ENDPOINT_SUFFIX = config.get('IRIDA',
                                                    'token_endpoint_suffix')
            self.INITIAL_ENDPOINT_SUFFIX = config.get('IRIDA',
                                                      'initial_endpoint_suffix')

            irida_loc = config.get('IRIDA', 'irida_url')
            self.TOKEN_ENDPOINT = irida_loc + self.TOKEN_ENDPOINT_SUFFIX
            irida_endpoint = irida_loc+self.INITIAL_ENDPOINT_SUFFIX

            self.CLIENT_ID = config.get('IRIDA', 'client_id')
            self.CLIENT_SECRET = config.get('IRIDA', 'client_secret')

            # Configure the tool XML file
            # The Galaxy server must be restarted for XML configuration
            # changes to take effect.
            # The XML file is only changed to reflect the IRIDA URL
            # and IRIDA client ID
            xml_path = os.path.join(parent_folder, self.XML_FILE)
            tree = ElementTree.parse(xml_path)

            inputs = tree.find('inputs')
            inputs.set('action', irida_endpoint)
            params = inputs.findall('param')
            client_id_param = next(param for param in params
                                   if param.get('name') == self.CLIENT_ID_PARAM)
            client_id_param.set('value', self.CLIENT_ID)

            tree.write(xml_path)

    def import_to_galaxy(self, json_parameter_file, log, token=None,
                         config_file=None):
        """
        Import samples and their sample files into Galaxy from IRIDA

        :type json_parameter_file: str
        :param json_parameter_file: a path that Galaxy passes,
        to the stub datasource it created
        :type log: str
        :param log: the name of a file to write the tool's log to.
        :type token: str
        :param token: An access token that can be passed to the tool when it
        is manually run.
        :type config_file: str
        :param config_file: the name of a file to configure from
        """
        #self.logger = logging.getLogger('irida_import')
        self.logger.setLevel(logging.INFO)
        self.configure()
        with open(json_parameter_file, 'r') as param_file_handle:

            full_param_dict = json.loads(param_file_handle.read())
            param_dict = full_param_dict['param_dict']
            json_params_dict = json.loads(param_dict['json_params'])

            self.print_logged("Importing files from IRIDA to Galaxy...")

            self.uploaded_files_log = []
            self.skipped_files_log = []

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
                self.logger.debug("sample name is" + sample.name)
                self.create_folder_if_nec(self.ILLUMINA_PATH+'/'+sample.name)
                self.add_sample_if_nec(sample)
            self.print_summary()

"""
From the command line, pass JSON files to IridaImport, and set up the logger
"""
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-p', '--json_parameter_file', dest='json_parameter_file',
        default='sample.dat',
        help='A JSON formatted parameter file from Galaxy', metavar='json_parameter_file')
    parser.add_argument(
        '-l', '--log-file', dest='log', default='log_file',
        help="The file to log the tool's output to", metavar='log')
    parser.add_argument(
        '-t', '--token', dest='token',
        help='The tool can use a supplied access token instead of querying IRIDA', metavar='token')
    parser.add_argument(
        '-c', '--config', action='store_true', default=False, dest='config',
        help='The tool must configure itself before Galaxy can be started. Use this option to do so. config.ini should be in the main irida_import folder.')

    args = parser.parse_args()
    if len(sys.argv)==1:
        parser.print_help()
        sys.exit(1)
    log_format = "%(levelname)s: %(message)s"
    logging.basicConfig(filename=args.log,
                        format=log_format,
                        level=logging.ERROR,
                        filemode="w")

    importer = IridaImport()
    logging.debug("Reading from passed file")

    if args.config:
        importer.configure()
        message = 'Configured XML file'
        logging.info(message)
        print message
    else:
        try:
            file_to_open = args.json_parameter_file
            importer.import_to_galaxy(file_to_open, args.log, token=args.token)
        except Exception:
            logging.exception('')
            importer.print_summary(failed=True)
            raise
