#!/bin/bash -e
virtualenv venv
source venv/bin/activate
pip install -U bioblend pytest pytest-cov pytest-mock requests==2.6 requests-oauthlib==0.4.2 subprocess32 selenium

# Install chromedriver
CHROME_DRIVER_VERSION=75.0.3770.140
echo "Downloading Chromedriver Version: $CHROME_DRIVER_VERSION"
wget --no-verbose -O /tmp/chromedriver_linux64.zip https://chromedriver.storage.googleapis.com/$CHROME_DRIVER_VERSION/chromedriver_linux64.zip
unzip /tmp/chromedriver_linux64.zip -d venv/bin
chmod 755 venv/bin/chromedriver
