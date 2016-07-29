""" EC2Endpoint class is the implementation of the EC2 interface to
    a cloud endpoint
"""

import os
import json
import boto3

from DIRAC import gLogger, S_OK, S_ERROR
from DIRAC.Core.Utilities.File import makeGuid

from VMDIRAC.Resources.Cloud.Endpoint import Endpoint
from VMDIRAC.Resources.Cloud.Utilities import createMimeData

__RCSID__ = '$Id$'

class EC2Endpoint( Endpoint ):

  def __init__( self, parameters = {} ):
    """
    """
    Endpoint.__init__( self, parameters = parameters )
    # logger
    self.log = gLogger.getSubLogger( 'EC2Endpoint' )
    self.valid = False
    result = self.initialize()
    if result['OK']:
      self.log.debug( 'EC2Endpoint created and validated' )
      self.valid = True
    else:
      self.log.error( result['Message'] )

  def initialize( self ):

    availableParams = {
      'RegionName': 'region_name',
      'AccessKey': 'aws_access_key_id',
      'SecretKey': 'aws_secret_access_key',
      'EndpointUrl': 'endpoint_url',          # EndpointUrl is optional
    }

    connDict = {}
    for var in availableParams:
      if var in self.parameters:
        connDict[ availableParams[ var ] ] = self.parameters[ var ]

    try:
      self.__ec2 = boto3.resource( 'ec2', **connDict )
    except Exception, e:
      errorStatus = "Can't connect to EC2: " + str(e)
      return S_ERROR( errorStatus )

    result = self.__loadInstanceType()
    if not result['OK']:
      return result

    result = self.__checkConnection()
    return result

  def __loadInstanceType( self ):
    currentDir = os.path.dirname( os.path.abspath( __file__ ) )
    instanceTypeFile = os.path.join( currentDir, 'ec2_instance_type.json' )
    try:
      with open( instanceTypeFile, 'r' ) as f:
        self.__instanceTypeInfo = json.load( f )
    except Exception, e:
      errmsg = "Exception loading EC2 instance type info: %s" % e
      self.log.error(  errmsg )
      return S_ERROR( errmsg )

    return S_OK()

  def __checkConnection( self ):
    """
    Checks connection status by trying to list the images.

    :return: S_OK | S_ERROR
    """
    try:
      self.__ec2.images.filter( Owners = ['self'] )
    except Exception, e:
      return S_ERROR( e )

    return S_OK()

  def __createUserDataScript( self ):

    userDataDict = {}

    # Arguments to the vm-bootstrap command
    bootstrapArgs = { 'dirac-site': self.parameters['Site'],
#                      'submit-pool': self.parameters['SubmitPool'],
                      'ce-name': self.parameters['CEName'],
                      'image-name': self.parameters['Image'],
                      'vm-uuid': self.parameters['VMUUID'],
                      'vmtype': self.parameters['VMType'],
                      'vo': self.parameters['VO'],
                      'running-pod': self.parameters['RunningPod'],
                      'cvmfs-proxy': self.parameters.get( 'CVMFSProxy', 'None' ),
                      'cs-servers': ','.join( self.parameters.get( 'CSServers', [] ) ),
                      'release-version': self.parameters['Version'] ,
                      'release-project': self.parameters['Project'] ,
                      'setup': self.parameters['Setup'] }

    bootstrapString = ''
    for key, value in bootstrapArgs.items():
      bootstrapString += " --%s=%s \\\n" % ( key, value )
    userDataDict['bootstrapArgs'] = bootstrapString

    userDataDict['user_data_commands_base_url'] = self.parameters.get( 'user_data_commands_base_url' )
    if not userDataDict['user_data_commands_base_url']:
      return S_ERROR( 'user_data_commands_base_url is not defined' )
    with open( self.parameters['HostCert'] ) as cfile:
      userDataDict['user_data_file_hostkey'] = cfile.read().strip()
    with open( self.parameters['HostKey'] ) as kfile:
      userDataDict['user_data_file_hostcert'] = kfile.read().strip()

    # List of commands to be downloaded
    bootstrapCommands = self.parameters.get( 'user_data_commands' )
    if isinstance( bootstrapCommands, basestring ):
      bootstrapCommands = bootstrapCommands.split( ',' )
    if not bootstrapCommands:
      return S_ERROR( 'user_data_commands list is not defined' )
    userDataDict['bootstrapCommands'] = ' '.join( bootstrapCommands )

    script = """
cat <<X5_EOF >/root/hostkey.pem
%(user_data_file_hostkey)s
%(user_data_file_hostcert)s
X5_EOF
mkdir -p /var/spool/checkout/context
cd /var/spool/checkout/context
for dfile in %(bootstrapCommands)s
do
  echo curl --insecure -s %(user_data_commands_base_url)s/$dfile -o $dfile
  i=7
  while [ $i -eq 7 ]
  do
    curl --insecure -s %(user_data_commands_base_url)s/$dfile -o $dfile
    i=$?
    if [ $i -eq 7 ]; then
      echo curl connection failure for file $dfile
      sleep 10
    fi
  done
  curl --insecure -s %(user_data_commands_base_url)s/$dfile -o $dfile || echo Download of $dfile failed with $? !
done
chmod +x vm-bootstrap
/var/spool/checkout/context/vm-bootstrap %(bootstrapArgs)s
#/sbin/shutdown -h now
    """ % userDataDict

    if "HEPIX" in self.parameters:
      script = """
cat <<EP_EOF >>/var/lib/hepix/context/epilog.sh
#!/bin/sh
%s
EP_EOF
chmod +x /var/lib/hepix/context/epilog.sh
      """ % script

    user_data = """#!/bin/bash
mkdir -p /etc/joboutputs
(
%s
) > /etc/joboutputs/user_data.log 2>&1 &
exit 0
    """ % script

    cloud_config = """#cloud-config

output: {all: '| tee -a /var/log/cloud-init-output.log'}

cloud_final_modules:
  - [scripts-user, always]
    """

    return createMimeData( ( ( user_data, 'text/x-shellscript', 'dirac_boot.sh' ),
                             ( cloud_config, 'text/cloud-config', 'cloud-config') ) )

  def createInstances( self, vmsToSubmit ):
    outputDict = {}

    for nvm in xrange( vmsToSubmit ):
      instanceID = makeGuid()[:8]
      result = self.createInstance( instanceID )
      if result['OK']:
        ec2Id, nodeDict = result['Value']
        self.log.debug( 'Created VM instance %s/%s' % ( ec2Id, instanceID ) )
        outputDict[ec2Id] = nodeDict
      else:
        break

    return S_OK( outputDict )

  def createInstance( self, instanceID = ''  ):
    if not instanceID:
      instanceID = makeGuid()[:8]

    self.parameters['VMUUID'] = instanceID
    self.parameters['VMType'] = self.parameters.get( 'CEType', 'EC2' )

    createNodeDict = {}

    # Image
    if not "ImageID" in self.parameters and 'ImageName' in self.parameters:
      try:
        images = self.__ec2.images.filter( Filters = [{'Name': 'name', 'Values': [self.parameters['ImageName']]}] )
        imageId = None
        for image in images:
          imageId = image.id
          break
      except Exception as e:
        return S_ERROR( "Failed to get image for Name %s" % self.parameters['ImageName'] )
      if imageId is None:
        return S_ERROR( "Image name %s not found" % self.parameters['ImageName'] )
    elif "ImageID" in self.parameters:
      try:
        self.__ec2.images.filter( ImageIds = [self.parameters['ImageID']] )
      except Exception as e:
        return S_ERROR( "Failed to get image for ID %s" % self.parameters['ImageID'] )
      imageId = self.parameters['ImageID']
    else:
      return S_ERROR( 'No image specified' )
    createNodeDict['ImageId'] = imageId

    # Instance type
    if 'FlavorName' not in self.parameters:
      return S_ERROR( 'No flavor specified' )
    instanceType = self.parameters['FlavorName']
    createNodeDict['InstanceType'] = instanceType

    # User data
    result = self.__createUserDataScript()
    if not result['OK']:
      return result
    createNodeDict['UserData'] = str( result['Value'] )

    # Other params
    for param in [ 'KeyName', 'SubnetId', 'EbsOptimized' ]:
      if param in self.parameters:
        createNodeDict[param] = self.parameters[param]

    self.log.info( "Creating node:" )
    for key, value in createNodeDict.items():
      self.log.verbose( "%s: %s" % ( key, value ) )

    # Create the VM instance now
    try:
      instances = self.__ec2.create_instances( MinCount = 1, MaxCount = 1, **createNodeDict )
    except Exception as e:
      errmsg = 'Exception in ec2 create_instances: %s' % e
      self.log.error( errmsg )
      return S_ERROR( errmsg )

    if len(instances) < 1:
      errmsg = 'ec2 create_instances failed to create any VM'
      self.log.error( errmsg )
      return S_ERROR( errmsg )

    # Create the name in tags
    ec2Id = instances[0].id
    tags = [{ 'Key': 'Name', 'Value': 'DIRAC_%s' % instanceID }]
    try:
      self.__ec2.create_tags( Resources = [ec2Id], Tags = tags )
    except Exception as e:
      errmsg = 'Exception setup name for %s: %s' % ( ec2Id, e )
      self.log.error( errmsg )
      return S_ERROR( errmsg )

    # Properties of the instance
    nodeDict = {}
#    nodeDict['PublicIP'] = publicIP
    nodeDict['InstanceID'] = instanceID
    if instanceType in self.__instanceTypeInfo:
      nodeDict['NumberOfCPUs'] = self.__instanceTypeInfo[instanceType]['vCPU']
      nodeDict['RAM'] = self.__instanceTypeInfo[instanceType]['Memory']
    else:
      nodeDict['NumberOfCPUs'] = 1

    return S_OK( ( ec2Id, nodeDict ) )

  def stopVM( self, nodeID, publicIP = '' ):
    """
    Given the node ID it gets the node details, which are used to destroy the
    node making use of the libcloud.openstack driver. If three is any public IP
    ( floating IP ) assigned, frees it as well.

    :Parameters:
      **uniqueId** - `string`
        openstack node id ( not uuid ! )
      **public_ip** - `string`
        public IP assigned to the node if any

    :return: S_OK | S_ERROR
    """
    try:
      self.__ec2.Instance( nodeID ).terminate()
    except Exception as e:
      errmsg = 'Exception terminate instance %s: %s' % ( nodeID, e )
      self.log.error( errmsg )
      return S_ERROR( errmsg )

    return S_OK()
