#!/bin/bash
#
# cvmfs configuration for boss repository: 
# to be run as root on the VM
#
#

if [ $# -ne 1 ]
then
	echo "cvmfs-boss-context.sh <cvmfs_http_proxy>"
fi	



cat << EOF > /etc/cvmfs/default.local
CVMFS_REPOSITORIES=boss.cern.ch
CVMFS_HTTP_PROXY=$1
CVMFS_CACHE_BASE=/scratch/cvmfs/cache
CVMFS_QUOTA_LIMIT=4096
EOF

# reaload configuration to activate new setup:
/sbin/service autofs restart >> /var/log/cvmfs-boss-script.log 2>&1
cvmfs_config showconfig >> /var/log/cvmfs-boss-script.log 2>&1
cvmfs_config probe >> /var/log/cvmfs-boss-script.log 2>&1

exit 0
