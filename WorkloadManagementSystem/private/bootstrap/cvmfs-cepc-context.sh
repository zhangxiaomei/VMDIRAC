#!/bin/bash
#
# cvmfs configuration for cepc repository: 
# to be run as root on the VM
#
#

if [ $# -ne 1 ]
then
	echo "cvmfs-cepc-context.sh <cvmfs_http_proxy>"
fi	

wget http://badger02.ihep.ac.cn/pub/bes/cvmfs/cepc-patch.sh -o /root/cepc-patch.sh >> /var/log/cvmfs-cepc-script.log 2>&1
chmod +x cepc-patch.sh
/root/cepc-patch.sh >> /var/log/cvmfs-cepc-script.log 2>&1


cat << EOF > /etc/cvmfs/default.local
CVMFS_REPOSITORIES=boss.cern.ch,cepc.ihep.ac.cn
CVMFS_HTTP_PROXY=$1
CVMFS_CACHE_BASE=/scratch/cvmfs/cache
CVMFS_QUOTA_LIMIT=4096
EOF

# reaload configuration to activate new setup:
/sbin/service autofs restart >> /var/log/cvmfs-cepc-script.log 2>&1
cvmfs_config showconfig >> /var/log/cvmfs-cepc-script.log 2>&1
cvmfs_config probe >> /var/log/cvmfs-cepc-script.log 2>&1

exit 0
