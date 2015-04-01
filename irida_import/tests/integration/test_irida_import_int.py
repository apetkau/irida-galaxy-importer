import os
import pytest
import subprocess32
from splinter import Browser
from ...irida_import import IridaImport
import inspect
from . import util
import getpass


@pytest.mark.integration
class TestIridaImportInt:

    INSTALL = True  # Install or update Galaxy, IRIDA, and the export tool
    START = True  # Start Galaxy and IRIDA instances

    TIMEOUT = 200  # seconds

    GALAXY_DOMAIN = 'localhost'
    GALAXY_PORT = 8888
    GALAXY_URL = 'http://'+GALAXY_DOMAIN+':'+str(GALAXY_PORT)
    GALAXY_CMD = ['bash', 'run.sh']

    IRIDA_DOMAIN = 'localhost'
    IRIDA_PORT = 8080
    IRIDA_URL = 'http://'+IRIDA_DOMAIN+':'+str(IRIDA_PORT)
    IRIDA_CMD = ['mvn', 'clean', 'jetty:run',
                 '-Djdbc.url=jdbc:mysql://localhost:3306/irida_test',
                 '-Djdbc.username=test', '-Djdbc.password=test',
                 '-Dliquibase.update.database.schema=true',
                 '-Dhibernate.hbm2ddl.auto=',
                 '-Dhibernate.hbm2ddl.import_files='
                 '-DSTOP.PORT=8080', '-DSTOP.KEY=stop']

    INSTALL_EXEC = 'install.sh'
    PASTER_SIG = '\"python ./scripts/paster.py\"'

    def setup_class(self):
        module_dir = os.path.dirname(os.path.abspath(__file__))
        self.SCRIPTS = os.path.join(module_dir, 'bash_scripts')
        self.REPOS = os.path.join(module_dir, 'repos')
        self.TOOL_DIRECTORY = os.path.dirname(inspect.getfile(IridaImport))

        self.GALAXY = os.path.join(self.REPOS, 'galaxy')
        self.IRIDA = os.path.join(self.REPOS, 'irida')

        if self.INSTALL:
            # Install IRIDA, Galaxy, and the IRIDA export tool:
            exec_path = os.path.join(self.SCRIPTS, self.INSTALL_EXEC)
            install = subprocess32.Popen(
                [exec_path, self.TOOL_DIRECTORY], cwd=self.REPOS)
            install.wait()  # Block untill installed

    @pytest.fixture(scope='class')
    def browser(self, request):
        browser = Browser('chrome')

        def finalize_browser():
            browser.quit()
        request.addfinalizer(finalize_browser)
        return browser

    @pytest.fixture(scope='class')
    def setup_irida(self, request, browser):
        if self.START:
            # TODO: command jetty to stop
            subprocess32.call(
                ['pkill', '-u', getpass.getuser(),
                 '-f', '\"'+self.IRIDA_CMD[1]+'\"'])
            irida = subprocess32.Popen(self.IRIDA_CMD, cwd=self.IRIDA)
            util.wait_until_up(self.IRIDA_DOMAIN, self.IRIDA_PORT, self.TIMEOUT)

            def finalize_irida():
                print 'Killing IRIDA'
                irida.kill()
            request.addfinalizer(finalize_irida)
        self.register_irida(browser)

    @pytest.fixture(scope='class')
    def setup_galaxy(self, request, browser):
        if self.START:
            # Make very sure Galaxy is not running:
            subprocess32.call(
                ['pkill', '-u', getpass.getuser(), '-f', self.PASTER_SIG])
            galaxy = subprocess32.Popen(self.GALAXY_CMD, cwd=self.GALAXY)
            util.wait_until_up(
                self.GALAXY_DOMAIN,
                self.GALAXY_PORT,
                self.TIMEOUT)

            def finalize_galaxy():
                print 'Killing Galaxy'
                galaxy.kill()
            request.addfinalizer(finalize_galaxy)
        self.register_galaxy(browser)

    def test_configured(self, setup_irida, setup_galaxy, browser):
        return True

    def register_galaxy(self, browser):
        browser.visit(self.GALAXY_URL)
        return True

    def register_irida(self, browser):
        browser.visit(self.IRIDA_URL)
        return True
