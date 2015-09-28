# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

# This file is part of Guadalinex
#
# This software is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this package; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA

__author__ = "Abraham Macias Paredes <amacias@solutia-it.es>"
__copyright__ = "Copyright (C) 2015, Junta de Andalucía <devmaster@guadalinex.org>"
__license__ = "GPL-2"

import sys

if 'check' in sys.argv:
    # Mock view classes for testing purposses
    print "==> Loading mocks..."
    from view.ViewMocks import showerror, ConnectWithGecosCCDialog, ChefValidationCertificateDialog, GecosCCSetupProcessView
else:
    # Use real view classes
    from view.ConnectWithGecosCCDialog import ConnectWithGecosCCDialog
    from view.ChefValidationCertificateDialog import ChefValidationCertificateDialog
    from view.GecosCCSetupProcessView import GecosCCSetupProcessView
    from view.CommonDialog import showerror

from util.GecosCC import GecosCC
from util.Validation import Validation
from util.Template import Template

from dao.GecosAccessDataDAO import GecosAccessDataDAO
from dao.WorkstationDataDAO import WorkstationDataDAO
from dao.NetworkInterfaceDAO import NetworkInterfaceDAO



import logging
import hashlib
import socket
import fcntl
import struct
import traceback
import os
import pwd
import grp
import subprocess
import base64

import gettext
from gettext import gettext as _
gettext.textdomain('gecosws-config-assistant')


class ConnectWithGecosCCController(object):
    '''
    Controller class for the "connect/disconnect with GECOS CC" functionality.
    '''


    def __init__(self):
        '''
        Constructor
        '''
        self.view = None # TODO!
        self.accessDataDao = GecosAccessDataDAO()
        self.workstationDataDao = WorkstationDataDAO()
        self.logger = logging.getLogger('ConnectWithGecosCCController')

    def show(self, mainWindow):
        self.logger.debug('show - BEGIN')
        self.view = ConnectWithGecosCCDialog(mainWindow, self)
        
        self.view.set_gecos_access_data(self.accessDataDao.load())
        self.view.set_workstation_data(self.workstationDataDao.load())
        
        self.view.show()   
        self.logger.debug('show - END')

    def hide(self):
        self.logger.debug("hide")
        self.view.cancel()
    
    def _check_gecosConnectionParameters(self, gecosAccessData):
        self.logger.debug("_check_gecosConnectionParameters")
        # Validate Gecos access data
        if (gecosAccessData.get_url() is None or
            gecosAccessData.get_url().strip() == ''):
            self.logger.debug("Empty URL!")
            showerror(_("Error in form data"), 
                _("The URL field is empty!") + "\n" + _("Please fill all the mandatory fields."),
                 self.view)
            self.view.focusUrlField()            
            return False

        if not Validation().isUrl(gecosAccessData.get_url()):
            self.logger.debug("Malformed URL!")
            showerror(_("Error in form data"), 
                _("Malformed URL in URL field!") + "\n" + _("Please double-check it."),
                 self.view)            
            self.view.focusUrlField()            
            return False

        if (gecosAccessData.get_login() is None or
            gecosAccessData.get_login().strip() == ''):
            self.logger.debug("Empty login!")
            showerror(_("Error in form data"), 
                _("The Username field is empty!") + "\n" + _("Please fill all the mandatory fields."),
                 self.view)
            self.view.focusUsernameField()            
            return False

        if (gecosAccessData.get_password() is None or
            gecosAccessData.get_password().strip() == ''):
            self.logger.debug("Empty password!")
            showerror(_("Error in form data"), 
                _("The Password field is empty!") + "\n" + _("Please fill all the mandatory fields."),
                 self.view)
            self.view.focusPasswordField()            
            return False

        gecosCC = GecosCC()
        if not gecosCC.validate_credentials(gecosAccessData):
            self.logger.debug("Bad access data!")
            showerror(_("Error in form data"), 
                _("Can't connect to GECOS CC!") + "\n" +  _("Please double-check all the data and your network setup."),
                 self.view)
            self.view.focusPasswordField()            
            return False
        
        return True

    def _getHwAddr(self, ifname):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        info = fcntl.ioctl(s.fileno(), 0x8927,  struct.pack('256s', ifname[:15]))
        return ''.join(['%02x:' % ord(char) for char in info[18:24]])[:-1]  

    def _check_workstation_data(self, workstationData):
        self.logger.debug("_check_workstation_data")
        # Validate Gecos workstation data
        if (workstationData.get_name() is None or
            workstationData.get_name().strip() == ''):
            self.logger.debug("Empty Node name!")
            showerror(_("Error in form data"), 
                _("The GECOS workstation name field is empty!") + "\n" + _("Please fill all the mandatory fields."),
                 self.view)
            self.view.focusWorkstationNameField()            
            return False     
        
        
        if workstationData.get_node_name() is None or workstationData.get_node_name().strip() == '':
            # Computer name must be unique
            gecosCC = GecosCC()
            computer_names = gecosCC.get_computer_names(self.view.get_gecos_access_data())
            is_in_computer_names = False
            for cn in computer_names:
                if cn['name'] == workstationData.get_name():
                    is_in_computer_names = True
                    break
                    
            
            if is_in_computer_names:  
                self.logger.debug("Existent node name!")
                showerror(_("Error in form data"), 
                    _("The GECOS workstation name already exist!") + "\n" + _("Please choose a different name."),
                     self.view)
                self.view.focusWorkstationNameField()            
                return False     
                    
            # Create a new node_name
            networkDao = NetworkInterfaceDAO()
            interfaces = networkDao.loadAll()
            no_localhost_name = None
            for inter in interfaces:
                if not inter.get_ip_address().startswith('127.0'):
                    no_localhost_name = inter.get_name()
                    break
            self.logger.debug("Selected interface name is: %s"%(no_localhost_name))
            mac = self._getHwAddr(no_localhost_name)
            node_name = hashlib.md5(mac.encode()).hexdigest()
            self.logger.debug("New node name is: %s"%(node_name))
            workstationData.set_node_name(node_name)

        if (workstationData.get_ou() is None or
            workstationData.get_ou().strip() == ''):
            self.logger.debug("Empty OU name!")
            showerror(_("Error in form data"), 
                _("You must select an OU!") + "\n" + _("Please fill all the mandatory fields."),
                 self.view)
            self.view.focusSeachFilterField()            
            return False   
        
        return True     

    def _remove_file(self, filename):
        try:
            if os.path.isfile(filename):
                os.remove(filename)
        except:
            self.logger.error("Error removing %s file"%(filename))
            self.logger.error(str(traceback.format_exc()))
            return False    
        
        return True
    
    def _save_secure_file(self, filename, filecontent):
        try:
            # Create empty file
            fd = open(filename, 'w')
            fd.truncate()
            fd.close()

            # Check the owner and permissions
            stat_info = os.stat(filename)
            uid = stat_info.st_uid
            gid = stat_info.st_gid

            current_usr = pwd.getpwuid(uid)[0]
            current_grp = grp.getgrgid(gid)[0]
            
            # Set the user to root
            if current_usr != 'root':
                uid = pwd.getpwnam('root').pw_uid
                if uid is None:
                    self.logger.error(_('Can not find user to be used as owner: ') + 'root')
                else:
                    os.chown(filename, uid, gid)  
                
            if current_grp != 'root':
                gid = grp.getgrnam('root').gr_gid
                if gid is None:
                    self.logger.error(_('Can not find group to be used as owner: ') + 'root')
                else:
                    os.chown(filename, uid, gid)  
                
            # Set permissions to 00600
            mode = 00600
            m = stat_info.st_mode & 00777
            if m != mode:
                os.chmod(filename, mode)

            # Write the content
            fd = open(filename, 'w')
            fd.write(filecontent)
            fd.close()

            
        except:
            self.logger.error("Error creating %s file"%(filename))
            self.logger.error(str(traceback.format_exc()))
            return False        
        
        
        return True
    
    def _execute_command(self, cmd, my_env={}):
        try:
            p = subprocess.Popen(cmd, shell=True, 
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.STDOUT,
                                 env=my_env)
            for line in p.stdout.readlines():
                self.logger.debug(line)
                    
            retval = p.wait()
            if retval != 0:
                self.logger.error('Error running command: %s'%(cmd))
                return False     
            
        except:
            self.logger.error('Error running command: %s'%(cmd))
            self.logger.error(str(traceback.format_exc()))
            return False        
        
        
        return True                  
    
    def connect(self):
        self.logger.debug("connect")

        self.processView = GecosCCSetupProcessView(self.view, self)
        self.processView.setLinkToChefLabel(_('Link to Chef'))
        self.processView.setRegisterInGecosLabel(_('Register in GECOS CC'))
        self.processView.show()

        
        # Check parameters
        self.logger.debug("Check parameters")
        self.processView.setCheckGecosCredentialsStatus(_('IN PROCESS'))
        
        if self.view.get_gecos_access_data() is None:
            self.logger.error("Strange error: GECOS access data is None")
            self.processView.setCheckGecosCredentialsStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            return False

        if self.view.get_workstation_data() is None:
            self.logger.error("Strange error: workstation data is None")
            self.processView.setCheckGecosCredentialsStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            return False

        
        if not self._check_gecosConnectionParameters(self.view.get_gecos_access_data()):
            self.processView.setCheckGecosCredentialsStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            return False
        
        self.processView.setCheckGecosCredentialsStatus(_('DONE'))
        self.processView.setCheckWorkstationDataStatus(_('IN PROCESS'))
        if not self._check_workstation_data(self.view.get_workstation_data()):
            self.processView.setCheckWorkstationDataStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            return False

        self.processView.setCheckWorkstationDataStatus(_('DONE'))
        self.processView.setChefCertificateRetrievalStatus(_('IN PROCESS'))

        
        # Get validation.pem from server
        self.logger.debug("Get validation.pem from server")
        gecosCC = GecosCC()
        conf = gecosCC.get_json_autoconf(self.view.get_gecos_access_data())
        chef_validation = None
        if (conf is not None 
            and conf.has_key("chef")
            and conf["chef"].has_key("chef_validation")):
            chef_validation = base64.decodestring(conf["chef"]["chef_validation"])
            self.logger.debug("validation.pem retrieved from GECOS auto conf")
        
        if chef_validation is None:
            # Ask the user for the validation.pem URL
            self.certificate_url_view.show(self.processView, self)
            if self.certificate_url_view.get_data() is None:
                self.processView.setChefCertificateRetrievalStatus(_('CANCELED'))
                self.processView.enableAcceptButton()
                return False
            else:
                chef_validation = self.certificate_url_view.get_data()

        # Save Chef validation certificate in a PEM file
        if not self._save_secure_file('/etc/chef/validation.pem', chef_validation):
            self.processView.setChefCertificateRetrievalStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            showerror(_("Error saving validation certificate"), 
                _("There was an error while saving validation certificate"),
                 self.view)
            return False

        self.processView.setChefCertificateRetrievalStatus(_('DONE'))
        self.processView.setLinkToChefStatus(_('IN PROCESS'))
        
        # Link to Chef
        self.logger.debug("Link to Chef")
        
        self.logger.debug("- Create /etc/chef/client.rb")
        
        workstationData = self.view.get_workstation_data()
        chef_admin_name = self.view.get_gecos_access_data().get_login()
        chef_url = self.view.get_gecos_access_data().get_url()
        chef_url = chef_url.split('//')[1].split(':')[0]
        chef_url = "https://" + chef_url + '/'        
        
        
        if (conf is not None 
            and conf.has_key("chef")
            and conf["chef"].has_key("chef_url")):
            chef_url = conf["chef"]["chef_server_uri"]
            self.logger.debug("chef_url retrieved from GECOS auto conf")        

        if (conf is not None 
            and conf.has_key("chef")
            and conf["chef"].has_key("chef_admin_name")):
            chef_admin_name = conf["chef"]["chef_admin_name"]
            self.logger.debug("chef_admin_name retrieved from GECOS auto conf")               
        
        template = Template()
        template.source = 'templates/client.rb'
        template.destination = '/etc/chef/client.rb'
        template.owner = 'root'
        template.group = 'root'
        template.mode = 00644
        template.variables = { 'chef_url':  chef_url,
                              'chef_admin_name':  chef_admin_name,
                              'chef_node_name':  workstationData.get_node_name()}                
        
        if not template.save():
            self.processView.setLinkToChefStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            showerror(_("Error linking to Chef"), 
                _("Can't create/modify /etc/chef/client.rb file"),
                 self.view)
            return False            
        
      

        self.logger.debug('- Linking the chef server ')
        env = {'LANG': 'es_ES.UTF-8', 'LC_ALL': 'es_ES.UTF-8', 'HOME': os.environ['HOME']}
        if not self._execute_command('chef-client -j /usr/share/gecosws-config-assistant/base.json', env):
            self.processView.setLinkToChefStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            showerror(_("Error unlinking from Chef"), 
                _("Can't link to chef server"),
                 self.view)
            return False 
        
        self.logger.debug('- Start chef client service ')
        self._execute_command('service chef-client start')
        
        self.logger.debug('- Create a control file ')
        template = Template()
        template.source = 'templates/chef.control'
        template.destination = '/etc/chef.control'
        template.owner = 'root'
        template.group = 'root'
        template.mode = 00755
        template.variables = { 'chef_url':  chef_url,
                              'chef_admin_name':  chef_admin_name,
                              'chef_node_name':  workstationData.get_node_name()}                
        
        if not template.save():
            self.processView.setLinkToChefStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            showerror(_("Error linking to Chef"), 
                _("Can't create/modify /etc/chef/client.rb file"),
                 self.view)
            return False    
    
        
        
        self.processView.setLinkToChefStatus(_('DONE'))
        self.processView.setRegisterInGecosStatus(_('IN PROCESS'))
        
        # Register from GECOS Control Center
        self.logger.debug('- register in GECOS CC ')
        ou = gecosCC.search_ou_by_text(self.view.get_gecos_access_data(), 
                                  workstationData.get_ou())
        
        if not gecosCC.register_computer(self.view.get_gecos_access_data(), 
                workstationData.get_node_name(), ou[0][0]):
            self.processView.setRegisterInGecosStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            showerror(_("Error registering from GECOS CC"), 
                _("Can't register the computer in GECOS CC"),
                 self.view)
            return False          
        

        if not self.accessDataDao.save(self.view.get_gecos_access_data()):
            self.processView.setRegisterInGecosStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            showerror(_("Error Registering from GECOS CC"), 
                _("Can't save /etc/gcc.control file"),
                 self.view)
            return False    
        
        self.processView.setRegisterInGecosStatus(_('DONE'))
        self.processView.setCleanStatus(_('IN PROCESS'))
        
        # Clean setup files
        self._remove_file('/etc/chef/validation.pem')
        
        self.processView.setCleanStatus(_('DONE'))
        self.processView.enableAcceptButton()
        
        return True

        
    def disconnect(self):
        self.logger.debug("disconnect")
        
        self.processView = GecosCCSetupProcessView(self.view, self)
        self.processView.setLinkToChefLabel(_('Unlink from Chef'))
        self.processView.setRegisterInGecosLabel(_('Unregister from GECOS CC'))
        self.processView.show()
        
        # Check parameters
        self.logger.debug("Check parameters")
        self.processView.setCheckGecosCredentialsStatus(_('IN PROCESS'))
        if not self._check_gecosConnectionParameters(self.view.get_gecos_access_data()):
            self.processView.setCheckGecosCredentialsStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            return False
        
        self.processView.setCheckGecosCredentialsStatus(_('DONE'))
        self.processView.setCheckWorkstationDataStatus(_('IN PROCESS'))
        if not self._check_workstation_data(self.view.get_workstation_data()):
            self.processView.setCheckWorkstationDataStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            return False

        self.processView.setCheckWorkstationDataStatus(_('DONE'))
        self.processView.setChefCertificateRetrievalStatus(_('IN PROCESS'))

        
        # Get validation.pem from server
        self.logger.debug("Get validation.pem from server")
        gecosCC = GecosCC()
        conf = gecosCC.get_json_autoconf(self.view.get_gecos_access_data())
        chef_validation = None
        if (conf is not None 
            and conf.has_key("chef")
            and conf["chef"].has_key("chef_validation")):
            chef_validation = base64.decodestring(conf["chef"]["chef_validation"])
            self.logger.debug("validation.pem retrieved from GECOS auto conf")
        
        if chef_validation is None:
            # Ask the user for the validation.pem URL
            self.certificate_url_view = ChefValidationCertificateDialog(self.processView, self)
            self.certificate_url_view.show(self.processView, self)
            if self.certificate_url_view.get_data() is None:
                self.processView.setChefCertificateRetrievalStatus(_('CANCELED'))
                self.processView.enableAcceptButton()
                return False
            else:
                chef_validation = self.certificate_url_view.get_data()

        # Save Chef validation certificate in a PEM file
        if not self._save_secure_file('/etc/chef/validation.pem', chef_validation):
            self.processView.setChefCertificateRetrievalStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            showerror(_("Error saving validation certificate"), 
                _("There was an error while saving validation certificate"),
                 self.view)
            return False

        self.processView.setChefCertificateRetrievalStatus(_('DONE'))
        self.processView.setLinkToChefStatus(_('IN PROCESS'))
        
        # Unlink from Chef
        self.logger.debug("Unlink from Chef")
        
        self.logger.debug("- Set /etc/chef/client.rb with default values")
        template = Template()
        template.source = 'templates/client.rb'
        template.destination = '/etc/chef/client.rb'
        template.owner = 'root'
        template.group = 'root'
        template.mode = 00644
        template.variables = { 'chef_url':  'CHEF_URL',
                              'chef_admin_name':  'ADMIN_NAME',
                              'chef_node_name':  'NODE_NAME'}                
        
        if not template.save():
            self.processView.setLinkToChefStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            showerror(_("Error unlinking from Chef"), 
                _("Can't create/modify /etc/chef/client.rb file"),
                 self.view)
            return False            
        
        self.logger.debug("- Prepare /etc/chef/knife.rb")
        chef_admin_name = self.view.get_gecos_access_data().get_login()
        chef_url = self.view.get_gecos_access_data().get_url()
        chef_url = chef_url.split('//')[1].split(':')[0]
        chef_url = "https://" + chef_url + '/'        
        
        
        if (conf is not None 
            and conf.has_key("chef")
            and conf["chef"].has_key("chef_url")):
            chef_url = conf["chef"]["chef_server_uri"]
            self.logger.debug("chef_url retrieved from GECOS auto conf")        

        if (conf is not None 
            and conf.has_key("chef")
            and conf["chef"].has_key("chef_admin_name")):
            chef_admin_name = conf["chef"]["chef_admin_name"]
            self.logger.debug("chef_admin_name retrieved from GECOS auto conf")        

        
        template = Template()
        template.source = 'templates/knife.rb'
        template.destination = '/etc/chef/knife.rb'
        template.owner = 'root'
        template.group = 'root'
        template.mode = 00644
        template.variables = { 'chef_url':  chef_url,
                              'chef_admin_name':  chef_admin_name}                

        if not template.save():
            self.processView.setLinkToChefStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            showerror(_("Error unlinking from Chef"), 
                _("Can't create/modify /etc/chef/knife.rb file"),
                 self.view)
            return False 

        self.logger.debug("- Remove control file")
        if not self._remove_file('/etc/chef.control'):
            self.processView.setLinkToChefStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            showerror(_("Error unlinking from Chef"), 
                _("Can't remove /etc/chef.control file"),
                 self.view)
            return False 

        self.logger.debug("- Remove client.pem")
        if not self._remove_file('/etc/chef/client.pem'):
            self.processView.setLinkToChefStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            showerror(_("Error unlinking from Chef"), 
                _("Can't remove /etc/chef/client.pem file"),
                 self.view)
            return False 

        workstationData = self.view.get_workstation_data()
        self.logger.debug('- Deleting node ' + workstationData.get_node_name())
        if not self._execute_command('knife node delete "' + workstationData.get_node_name() + '" -c /etc/chef/knife.rb -y'):
            self.processView.setLinkToChefStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            showerror(_("Error unlinking from Chef"), 
                _("Can't delete Chef node"),
                 self.view)
            return False 
        
        self.logger.debug("- Remove chef-client-wrapper")
        if not self._remove_file('/usr/bin/chef-client-wrapper'):
            self.processView.setLinkToChefStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            showerror(_("Error unlinking from Chef"), 
                _("Can't remove /usr/bin/chef-client-wrapper file"),
                 self.view)
            return False         

        self.logger.debug('- Deleting client ' + workstationData.get_node_name())
        if not self._execute_command('knife client delete "' + workstationData.get_node_name() + '" -c /etc/chef/knife.rb -y'):
            self.processView.setLinkToChefStatus(_('ERROR'))
            showerror(_("Error unlinking from Chef"), 
                _("Can't delete Chef node"),
                 self.view)
            return False 

        self.logger.debug('- Stop chef client service ')
        self._execute_command('service chef-client stop')
        
        
        self.processView.setLinkToChefStatus(_('DONE'))
        self.processView.setRegisterInGecosStatus(_('IN PROCESS'))
        
        # Unregister from GECOS Control Center
        if not gecosCC.unregister_computer(self.view.get_gecos_access_data(), 
                workstationData.get_node_name()):
            self.processView.setRegisterInGecosStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            showerror(_("Error unregistering from GECOS CC"), 
                _("Can't unregister the computer from GECOS CC"),
                 self.view)
            return False          
        

        if not self.accessDataDao.delete(self.view.get_gecos_access_data()):
            self.processView.setRegisterInGecosStatus(_('ERROR'))
            self.processView.enableAcceptButton()
            showerror(_("Error unregistering from GECOS CC"), 
                _("Can't remove /etc/gcc.control file"),
                 self.view)
            return False    
        
        self.processView.setRegisterInGecosStatus(_('DONE'))
        self.processView.setCleanStatus(_('IN PROCESS'))
        
        # Clean setup files
        self._remove_file('/etc/chef/validation.pem')
        self._remove_file('/etc/chef/knife.rb')
        
        self.processView.setCleanStatus(_('DONE'))
        self.processView.enableAcceptButton()

        return True
        
        

    def patternSearch(self, searchText):
        self.logger.debug("patternSearch")
        
        if not self._check_gecosConnectionParameters(self.view.get_gecos_access_data()):
            return False
        
        
        gecosCC = GecosCC()
        result = gecosCC.search_ou_by_text(self.view.get_gecos_access_data(), searchText)
        if not isinstance(result, (list, tuple)):
            self.logger.debug("Can't get OUs from GECOS CC")
            showerror(_("Error getting data from GECOS CC"), 
                _("Can't get OUs from GECOS Control Center"),
                 self.view)
            self.view.focusPasswordField()            
            return False        
        
        return result 
        

    def proccess_dialog_accept(self):
        self.logger.debug("proccess_dialog_accept")