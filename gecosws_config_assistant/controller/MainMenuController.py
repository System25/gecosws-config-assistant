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

__author__ = "Abraham Macias Paredes <amacias@solutia-it.es> Francisco Fuentes Barrera <ffuentes@solutia-it.es>"
__copyright__ = "Copyright (C) 2015, Junta de Andalucía <devmaster@guadalinex.org>"
__license__ = "GPL-2"

from gettext import gettext as _
import gettext
from inspect import getmembers
import logging
import os, traceback
from pprint import pprint

from gecosws_config_assistant.controller.AutoSetupController import AutoSetupController
from gecosws_config_assistant.controller.ConnectWithGecosCCController import ConnectWithGecosCCController
from gecosws_config_assistant.controller.LocalUserController import LocalUserController
from gecosws_config_assistant.controller.NTPServerController import NTPServerController
from gecosws_config_assistant.controller.NetworkInterfaceController import NetworkInterfaceController
from gecosws_config_assistant.controller.RequirementsCheckController import RequirementsCheckController
from gecosws_config_assistant.controller.SystemStatusController import SystemStatusController
from gecosws_config_assistant.controller.UserAuthenticationMethodController import UserAuthenticationMethodController
from gecosws_config_assistant.controller.LogTerminalController import LogTerminalController
from gecosws_config_assistant.util.PackageManager import PackageManager 
from gecosws_config_assistant.view.CommonDialog import showerror_gtk, showinfo_gtk, askyesno_gtk
from gecosws_config_assistant.view.SplashScreen import SplashScreen
from gecosws_config_assistant.view.MainWindow import MainWindow
from gecosws_config_assistant.util.GtkAptProgress import GtkAptProgress
from gecosws_config_assistant.view.UserAuthDialog import UserAuthDialog, LOCAL_USERS, LDAP_USERS, AD_USERS

gettext.textdomain('gecosws-config-assistant')

class MainMenuController(object):
    '''
    Controller class to show the main menu window.
    '''
    
#     _singleton = None
#     
#     @classmethod
#     def getInstance(cls):
#         if not isinstance(cls._singleton,cls):
#             cls._singleton = cls()
#         return cls._singleton

    def __init__(self):
        '''
        Constructor
        '''
        self.logger = logging.getLogger('MainMenuController')
        self.window = MainWindow(self)
        self.logger.error(self.window)
        
        # controllers
        self.connectWithGecosCC = ConnectWithGecosCCController(self)
        self.userAuthenticationMethod = UserAuthenticationMethodController(self)
        self.localUserList = LocalUserController(self)
        self.systemStatus = SystemStatusController(self)
        self.logController = LogTerminalController(self)
        self.requirementsCheck = RequirementsCheckController(self)
        
        #keys
        self.networkStatusKey = "networkStatus"
        self.ntpStatusKey = "ntpStatus"
        self.autoconfStatusKey = "autoconf"
        self.gecosStatusKey = "gecos"
        self.usersStatusKey = "users"
        
        self.window.buildUI()
        self.showRequirementsCheckDialog()

    def show(self):
          
        self.checkForUpdates() 
        self.window.show()

    def hide(self):
        self.root.destroy()
    
    def calculateStatus(self):
        ret = {}
        
        ret[self.networkStatusKey] = 3
        ret[self.ntpStatusKey] = 3
        ret[self.autoconfStatusKey] = 3 
        ret[self.gecosStatusKey] = 3
        ret[self.usersStatusKey] = 3
        
        checkNetwork = self.checkNetwork()
        checkNTP = self.checkNTP()
        
        self.logger.debug('calculateStatus - network is: %s'%(checkNetwork));
        self.logger.debug('calculateStatus - NTP is: %s'%(checkNTP));
        
        if(checkNetwork):
            # Network is green
            ret[self.networkStatusKey] = 1
            
            
            if(checkNTP):
                # NTP is green
                ret[self.ntpStatusKey] = 1

            #self.logger.debug('calculateStatus - autoconf is: %s'%(self.checkAutoconf()));
            if(self.checkAutoconf()):
                # Auto configuration is green
                ret[self.autoconfStatusKey] = 1
            else:
                # Auto configuration is yellow
                ret[self.autoconfStatusKey] = 2
            
            if(checkNetwork and checkNTP):
                ret[self.gecosStatusKey] = 2
                ret[self.usersStatusKey] = 2
            
            self.logger.debug('calculateStatus - GECOS is: %s'%(self.checkGECOS()));
            if(self.checkGECOS()):
                ret[self.gecosStatusKey] = 1
            
            self.logger.debug('calculateStatus - Authentication is: %s'%(self.checkUsers()));
            if(self.checkUsers()):
                ret[self.usersStatusKey] = 1
        
        return ret
    
    def calculateMainButtons(self, calculatedStatus):
        ret = {}
        
        ret["netbutton" ] = True
        ret["confbutton"] = False
        ret["syncbutton"] = False 
        ret["sysbutton" ] = False
        ret["userbutton"] = False
        
        if(calculatedStatus[self.autoconfStatusKey] != 3):
            ret["confbutton"] = True
        
        if(calculatedStatus[self.ntpStatusKey] != 3):
            ret["syncbutton"] = True
        
        if(calculatedStatus[self.gecosStatusKey] != 3):
            ret["sysbutton" ] = True
        
        if(calculatedStatus[self.usersStatusKey] != 3):
            ret["userbutton"] = True
        
        return ret
    
    def calculateTopButtons(self, calculatedStatus):
        buttons = {}
        
        if(calculatedStatus[self.gecosStatusKey] != 3): 
            buttons["linkbutton"]= True
        else:
            buttons["linkbutton"]= False
            
        if(calculatedStatus[self.autoconfStatusKey] != 3):
            buttons["authbutton"]= True
        else:
            buttons["authbutton"]= False
        
        return buttons
    
    def getTexts(self):
        self.logger.debug("Calculating texts")
        text = {}
        
        if(self.checkNetwork()):
            text[self.networkStatusKey]  = _("The system has a network connection configured")
        else:
            text[self.networkStatusKey]  = _("The system has NO network connection")
        
        if self.checkAutoconf():
            text[self.autoconfStatusKey]     = _("The system has loaded setup data values from GECOS server")
        else:
            text[self.autoconfStatusKey]     = _("The system may load setup data values from GECOS server")
            
        if(self.checkNTP()):
            text[self.ntpStatusKey]      = _("The system is synchronized with a NTP server")
        else:
            text[self.ntpStatusKey]      = _("The system is NOT synchronized with a NTP server")
        
        if(self.checkGECOS()):
            text[self.gecosStatusKey]    = _("The system is linked to a GECOS server")
        else:
            text[self.gecosStatusKey]    = _("The system is NOT linked to a GECOS server")
        
        basetext = _("Users authenticate by %s method")
        
        status = self.userAuthenticationMethod.getStatus()
        
        if(status == LDAP_USERS):
            text[self.usersStatusKey]    = _(basetext)%( _("LDAP") )
        elif(status == AD_USERS):
            text[self.usersStatusKey]    = _(basetext)%( _("Active Directory"))
        else:
            text[self.usersStatusKey]    =  _(basetext)%( _("Internal"))
        
        return text
    
    def checkNetwork(self):
        self.logger.debug("Checking network status")
        ret = self.requirementsCheck.getNetworkStatus()
        return ret
    
    def getNetworkInterfaces(self):
        return self.requirementsCheck.getNetworkInterfaces()
    
    def checkNTP(self):
        self.logger.debug("Checking NTP status")
        ret = self.requirementsCheck.getNTPStatus()
        return ret
    
    def checkAutoconf(self):
        self.logger.debug("Checking Autoconf")
        ret = self.requirementsCheck.getAutoconfStatus()
        return ret
    
    def checkGECOS(self):
        self.logger.debug("Checking GECOS")
        ret = self.connectWithGecosCC.getStatus()
        return ret
    
    def checkUsers(self):
        self.logger.debug("Checking Users")
        ret = self.userAuthenticationMethod.areNotInternal()
        return ret
    
    # new show methods
    def backToMainWindowDialog(self):
        # restore main window
        self.showRequirementsCheckDialog()
    
    def showRequirementsCheckDialog(self):
        self.requirementsCheck.show(self.window)
        
        # Check status
        calculatedStatus = self.calculateStatus()
        calculatedButtons = self.calculateTopButtons(calculatedStatus)
        
        self.window.setStatus(calculatedStatus, calculatedButtons)
        

    def showConnectWithGecosCCDialog(self):
        self.connectWithGecosCC.show(self.window)

    def showUserAuthenticationMethod(self):
        view = self.userAuthenticationMethod.getView(self)
        self.window.gotoUserAuth(view)

    def showSoftwareManager(self):
        self.logger.debug("showSoftwareManager")
        cmd = '/usr/sbin/synaptic'
        os.spawnlp(os.P_NOWAIT, cmd, cmd)

    def showLocalUserListView(self):
        self.localUserList.showList(self.window)

    def checkForUpdates(self):

        import apt

        apt_progress = GtkAptProgress()
        cache = apt.cache.Cache(apt_progress.open)
        pkg = cache["gecosws-config-assistant"]

        if pkg.is_installed and pkg.is_upgradable:

            pkg.mark_upgrade()

            splash = SplashScreen()
            hbox2 = splash.getElementById('hbox2')
            hbox2.pack_start(apt_progress, True, True, 0)
            apt_progress.show()
            #self.splash.window.show_all()
            self.splash.show()

            button = splash.getElementById('label1')
            button.set_label(_('Upgrading ...'))

            # For testing purposes
            #pkg = cache["0ad-data"]
            #if pkg.is_installed:
            #    pkg.mark_delete()
            #else:
            #    pkg.mark_install()

            apt_progress.show_terminal(True)
            try:
                cache.commit(apt_progress.acquire, apt_progress.install)
            except Exception as exc:
                self.logger.debug("Exception happened: %s" % exc)

            splash.hide()


    def showSystemStatus(self):
        self.systemStatus.show()

    def showTerminalWindow(self):
        self.logController.show()

    def getNTPController(self):
        return self.requirementsCheck.ntpServer
