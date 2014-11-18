#!/bin/bash
#
# cvmfs configuration for ihep repository: 
# to be run as root on the VM
#
#

if [ $# -ne 1 ]
then
    echo "cvmfs-ihep-context.sh <cvmfs_http_proxy>"
fi	

sed -i "s+CVMFS_HTTP_PROXY\s*=.*+CVMFS_HTTP_PROXY=$1+" /etc/cvmfs/default.local

# reaload configuration to activate new setup:
/sbin/service autofs restart >> /var/log/cvmfs-boss-script.log 2>&1
cvmfs_config showconfig >> /var/log/cvmfs-boss-script.log 2>&1
cvmfs_config probe >> /var/log/cvmfs-boss-script.log 2>&1

exit 0
