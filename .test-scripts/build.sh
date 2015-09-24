#!/bin/sh
virtualenv env
source env/bin/activate
pip install -U bioblend pytest pytest-cov pytest-mock requests==2.6 requests-oauthlib==0.4.2 subprocess32 selenium
cd irida_import
xvfb-run py.test -s  
pip show bioblend
deactivate 
