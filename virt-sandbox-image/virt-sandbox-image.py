#!/usr/bin/python -Es
# -*- coding: utf-8 -*-
# Authors: Daniel P. Berrange <berrange@redhat.com>
#          Eren Yagdiran <erenyagdiran@gmail.com>
#
# Copyright (C) 2013 Red Hat, Inc.
# Copyright (C) 2015 Universitat Politècnica de Catalunya.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#

import argparse
import gettext
import hashlib
import json
import os
import os.path
import shutil
import sys
import urllib2
import subprocess

default_index_server = "index.docker.io"
default_template_dir = "/var/lib/libvirt/templates"

debug = True
verbose = True

sys.dont_write_bytecode = True

##Hook mechanism starts##
import __builtin__
from sources.Source import Source
__builtin__.hookHolder = {}
def add_hook(driverName,clazz):
    holder = __builtin__.hookHolder
    if not issubclass(clazz,Source):
        raise Exception("Loading %s failed. Make sure it is a subclass Of %s" %(clazz,Source))
    holder[driverName] = clazz

def init_from_name(name):
    holder = __builtin__.hookHolder
    return holder.get(name,None)

__builtin__.add_hook = add_hook
__builtin__.init_from_name = init_from_name
from sources import *

def dynamic_source_loader(name):
    obj = init_from_name(name)
    if obj == None:
        raise IOError
    return obj()
##Hook mechanism ends

gettext.bindtextdomain("libvirt-sandbox", "/usr/share/locale")
gettext.textdomain("libvirt-sandbox")
try:
    gettext.install("libvirt-sandbox",
                    localedir="/usr/share/locale",
                    unicode=False,
                    codeset = 'utf-8')
except IOError:
    import __builtin__
    __builtin__.__dict__['_'] = unicode


def debug(msg):
    sys.stderr.write(msg)

def info(msg):
    sys.stdout.write(msg)

def download(args):
    try:
        dynamic_source_loader(args.source).download_template(name=args.name,
                                                             registry=args.registry,
                                                             username=args.username,
                                                             password=args.password,
                                                             templatedir=args.template_dir)
    except IOError,e:
        print "Source %s cannot be found in given path" %args.source
    except Exception,e:
        print "Download Error %s" % str(e)

def delete(args):
    try:
        dynamic_source_loader(args.source).delete_template(name=args.name,
                                                           imagepath=args.imagepath)
    except Exception,e:
        print "Delete Error %s", str(e)

def create(args):
    try:
        dynamic_source_loader(args.source).create_template(name=args.name,
                                                           driver=args.driver,
                                                           imagepath=args.imagepath,
                                                           format=args.format)
    except Exception,e:
        print "Create Error %s" % str(e)

def check_driver(driver):
        supportedDrivers = ['lxc:///','qemu:///session','qemu:///system']
        if not driver in supportedDrivers:
            raise ValueError("%s is not supported by Virt-sandbox" %driver)
        return True

def run(args):
    try:
        default_dir = "/var/lib/libvirt/storage"
        check_driver(args.driver)
        source = dynamic_source_loader(args.source)
        diskfile,configfile = source.get_disk(name=args.name,path=args.imagepath)

        format = "qcow2"
        commandToRun = args.command
        if commandToRun is None:
            commandToRun = source.get_command(configfile)

        cmd = ['virt-sandbox',
               '-c',args.driver,
               '-m','host-image:/=%s,format=%s' %(diskfile,format)]

        networkArgs = args.network
        if networkArgs is not None:
            cmd.append('-N')
            cmd.append(networkArgs)

        allVolumes = source.get_volume(configfile)
        volumeArgs = args.volume
        if volumeArgs is not None:
            allVolumes = allVolumes + volumeArgs
        for volume in allVolumes:
            volumeSplit = volume.split(":")
            volumelen = len(volumeSplit)
            if volumelen == 2:
                hostPath = volumeSplit[0]
                guestPath = volumeSplit[1]
            elif volumelen == 1:
                guestPath = volumeSplit[0]
                hostPath = default_dir + guestPath
                if not os.path.exists(hostPath):
                    os.makedirs(hostPath)
            else:
                pass
            cmd.append("--mount")
            cmd.append("host-bind:%s=%s" %(guestPath,hostPath))

        cmd.append('--')
        cmd.append(commandToRun)
        subprocess.call(cmd)

    except Exception,e:
        print "Run Error %s" % str(e)

def requires_name(parser):
    parser.add_argument("name",
                        help=_("name of the template"))

def requires_source(parser):
    parser.add_argument("-s","--source",
                        default="docker",
                        help=_("name of the template"))

def requires_driver(parser):
    parser.add_argument("-d","--driver",
                        default="qemu:///session",
                        help=_("Type of the driver"))

def requires_auth_conn(parser):
    parser.add_argument("-r","--registry",
                        help=_("Url of the custom registry"))
    parser.add_argument("-u","--username",
                        help=_("Username for the custom registry"))
    parser.add_argument("-p","--password",
                        help=_("Password for the custom registry"))
    parser.add_argument("-t","--template-dir",
                        help=_("Template directory for saving templates"))

def gen_download_args(subparser):
    parser = subparser.add_parser("download",
                                   help=_("Download template data"))
    requires_source(parser)
    requires_name(parser)
    requires_auth_conn(parser)
    parser.set_defaults(func=download)

def gen_delete_args(subparser):
    parser = subparser.add_parser("delete",
                                   help=_("Delete template data"))
    requires_name(parser)
    requires_source(parser)
    parser.add_argument("imagepath",
                        help=_("Path for image"))
    parser.set_defaults(func=delete)

def gen_create_args(subparser):
    parser = subparser.add_parser("create",
                                   help=_("Create image from template data"))
    requires_name(parser)
    requires_source(parser)
    requires_driver(parser)
    parser.add_argument("imagepath",
                        help=_("path for image"))
    parser.add_argument("format",
                        help=_("format format for image"))
    parser.set_defaults(func=create)

def gen_run_args(subparser):
    parser = subparser.add_parser("run",
                                  help=_("Run a already built image"))
    requires_name(parser)
    requires_source(parser)
    requires_driver(parser)
    parser.add_argument("imagepath",
                        help=_("path for image"))
    parser.add_argument("-c","--command",
                        help=_("Igniter command for image"))
    parser.add_argument("-n","--network",
                        help=_("Network params for running template"))
    parser.add_argument("-v","--volume",action="append",
                        help=_("Volume params for running template"))
    parser.set_defaults(func=run)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Sandbox Container Image Tool')

    subparser = parser.add_subparsers(help=_("commands"))
    gen_download_args(subparser)
    gen_delete_args(subparser)
    gen_create_args(subparser)
    gen_run_args(subparser)

    try:
        args = parser.parse_args()
        args.func(args)
        sys.exit(0)
    except KeyboardInterrupt, e:
        sys.exit(0)
    except ValueError, e:
        for line in e:
            for l in line:
                sys.stderr.write("%s: %s\n" % (sys.argv[0], l))
        sys.stderr.flush()
        sys.exit(1)
    except IOError, e:
        sys.stderr.write("%s: %s: %s\n" % (sys.argv[0], e.filename, e.reason))
        sys.stderr.flush()
        sys.exit(1)
    except OSError, e:
        sys.stderr.write("%s: %s\n" % (sys.argv[0], e))
        sys.stderr.flush()
        sys.exit(1)
