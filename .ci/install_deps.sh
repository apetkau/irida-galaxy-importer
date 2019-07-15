#!/bin/bash -e
sudo pip install -U bioblend pytest pytest-cov pytest-mock requests==2.6 requests-oauthlib==0.4.2 subprocess32 selenium

# Install chromedriver
CHROME_DRIVER_VERSION=2.28
wget --no-verbose -O /tmp/chromedriver_linux64.zip https://chromedriver.storage.googleapis.com/$CHROME_DRIVER_VERSION/chromedriver_linux64.zip
rm -rf /opt/selenium/chromedriver
unzip /tmp/chromedriver_linux64.zip -d /opt/selenium
rm /tmp/chromedriver_linux64.zip
mv /opt/selenium/chromedriver /opt/selenium/chromedriver-$CHROME_DRIVER_VERSION
chmod 755 /opt/selenium/chromedriver-$CHROME_DRIVER_VERSION
ln -fs /opt/selenium/chromedriver-$CHROME_DRIVER_VERSION /usr/bin/chromedriver

echo '{ "allow_root": true }' > /root/.bowerrc
sed -i -e 's/localhost:3306/mysql:3306/g' irida_import/tests/integration/test_irida_import_int.py
sed -i -e 's/password=test/password=password/g' irida_import/tests/integration/test_irida_import_int.py
sed -i -e 's/mysql -u test -ptest/mysql -h mysql -u test -ppasswordg' irida_import/tests/integration/test_irida_import_int.py

sed -i -e 's/test:test@localhost/test:password@mysql/g' irida_import/tests/integration/bash_scripts/install.sh
