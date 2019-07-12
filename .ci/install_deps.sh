#!/bin/bash -e
sudo pip install -U bioblend pytest pytest-cov pytest-mock requests==2.6 requests-oauthlib==0.4.2 subprocess32 selenium

echo '{ "allow_root": true }' > /root/.bowerrc
sed -i -e 's/localhost:3306/mysql:3306/g' irida_import/tests/integration/test_irida_import_int.py
sed -i -e 's/password=test/password=password/g' irida_import/tests/integration/test_irida_import_int.py
sed -i -e 's/mysql -u test -ptest/mysql -h mysql -u test -ppasswordg' irida_import/tests/integration/test_irida_import_int.py

sed -i -e 's/test:test@localhost/test:password@mysql/g' irida_import/tests/integration/bash_scripts/install.sh
