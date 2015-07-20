#!/usr/bin/python

from Source import Source
import urllib2
import sys
import json
import traceback
import os
import subprocess
import shutil

class DockerSource(Source):
    default_index_server = "index.docker.io"
    default_template_dir = "/var/lib/libvirt/templates"
    default_image_path = "/var/lib/libvirt/templates"
    default_disk_format = "qcow2"

    www_auth_username = None
    www_auth_password = None

    def __init__(self,server="index.docker.io",destdir="/var/lib/libvirt/templates"):
        self.default_index_server = server
        self.default_template_dir = destdir

    def download_template(self,**args):
        name = args['name']
        registry = args['registry'] if args['registry'] is not None else self.default_index_server
        username = args['username']
        password = args['password']
        templatedir = args['templatedir'] if args['templatedir'] is not None else self.default_template_dir
        self.__download_template(name,registry,username,password,templatedir)

    def __download_template(self,name, server,username,password,destdir):

        if username is not None:
            self.www_auth_username = username
            self.www_auth_password = password

        tag = "latest"
        offset = name.find(':')
        if offset != -1:
            tag = name[offset + 1:]
            name = name[0:offset]
        try:
            (data, res) = self.__get_json(server, "/v1/repositories/" + name + "/images",
                               {"X-Docker-Token": "true"})
        except urllib2.HTTPError, e:
            raise ValueError(["Image '%s' does not exist" % name])

        registryserver = res.info().getheader('X-Docker-Endpoints')
        token = res.info().getheader('X-Docker-Token')
        checksums = {}
        for layer in data:
            pass
        (data, res) = self.__get_json(registryserver, "/v1/repositories/" + name + "/tags",
                           { "Authorization": "Token " + token })

        cookie = res.info().getheader('Set-Cookie')

        if not tag in data:
            raise ValueError(["Tag '%s' does not exist for image '%s'" % (tag, name)])
        imagetagid = data[tag]

        (data, res) = self.__get_json(registryserver, "/v1/images/" + imagetagid + "/ancestry",
                               { "Authorization": "Token "+token })

        if data[0] != imagetagid:
            raise ValueError(["Expected first layer id '%s' to match image id '%s'",
                          data[0], imagetagid])

        try:
            createdFiles = []
            createdDirs = []

            for layerid in data:
                templatedir = destdir + "/" + layerid
                if not os.path.exists(templatedir):
                    os.mkdir(templatedir)
                    createdDirs.append(templatedir)

                jsonfile = templatedir + "/template.json"
                datafile = templatedir + "/template.tar.gz"

                if not os.path.exists(jsonfile) or not os.path.exists(datafile):
                    res = self.__save_data(registryserver, "/v1/images/" + layerid + "/json",
                                { "Authorization": "Token " + token }, jsonfile)
                    createdFiles.append(jsonfile)

                    layersize = int(res.info().getheader("Content-Length"))

                    datacsum = None
                    if layerid in checksums:
                        datacsum = checksums[layerid]

                    self.__save_data(registryserver, "/v1/images/" + layerid + "/layer",
                          { "Authorization": "Token "+token }, datafile, datacsum, layersize)
                    createdFiles.append(datafile)

            index = {
                "name": name,
            }

            indexfile = destdir + "/" + imagetagid + "/index.json"
            print("Index file " + indexfile)
            with open(indexfile, "w") as f:
                 f.write(json.dumps(index))
        except Exception as e:
            traceback.print_exc()
            for f in createdFiles:
                try:
                    os.remove(f)
                except:
                    pass
            for d in createdDirs:
                try:
                    shutil.rmtree(d)
                except:
                    pass
    def __save_data(self,server, path, headers, dest, checksum=None, datalen=None):
        try:
            res = self.__get_url(server, path, headers)

            csum = None
            if checksum is not None:
                csum = hashlib.sha256()

            pattern = [".", "o", "O", "o"]
            patternIndex = 0
            donelen = 0

            with open(dest, "w") as f:
                while 1:
                    buf = res.read(1024*64)
                    if not buf:
                        break
                    if csum is not None:
                        csum.update(buf)
                    f.write(buf)

                    if datalen is not None:
                        donelen = donelen + len(buf)
                        debug("\x1b[s%s (%5d Kb of %5d Kb)\x1b8" % (
                            pattern[patternIndex], (donelen/1024), (datalen/1024)
                        ))
                        patternIndex = (patternIndex + 1) % 4

            debug("\x1b[K")
            if csum is not None:
                csumstr = "sha256:" + csum.hexdigest()
                if csumstr != checksum:
                    debug("FAIL checksum '%s' does not match '%s'" % (csumstr, checksum))
                    os.remove(dest)
                    raise IOError("Checksum '%s' for data does not match '%s'" % (csumstr, checksum))
            debug("OK\n")
            return res
        except Exception, e:
            debug("FAIL %s\n" % str(e))
            raise

    def __get_url(self,server, path, headers):
        url = "https://" + server + path
        debug("Fetching %s..." % url)

        req = urllib2.Request(url=url)
        if json:
            req.add_header("Accept", "application/json")
        for h in headers.keys():
            req.add_header(h, headers[h])

        #www Auth header starts
        if self.www_auth_username is not None:
            base64string = base64.encodestring('%s:%s' % (self.www_auth_username, self.www_auth_password)).replace('\n', '')
            req.add_header("Authorization", "Basic %s" % base64string)
        #www Auth header finish

        return urllib2.urlopen(req)

    def __get_json(self,server, path, headers):
        try:
            res = self.__get_url(server, path, headers)
            data = json.loads(res.read())
            debug("OK\n")
            return (data, res)
        except Exception, e:
            debug("FAIL %s\n" % str(e))
            raise

    def create_template(self,**args):
        name = args['name']
        driver = args['driver']
        path = args['imagepath'] 
        path = path if path is not None else self.default_image_path
        format = args['format'] 
        format = format if format is not None else self.default_disk_format

        self.__create_template(name,
                               driver,
                               path,
                               format,
                               path)

    def __create_template(self,name,driver,image_path,format,destdir):
        self.__check_disk_format(format)
        
        imagelist = self.__get_image_list(name,destdir)
        imagelist.reverse()

        parentImage = None
        for imagetagid in imagelist:
            templateImage = destdir + "/" + imagetagid + "/template." + format
            cmd = ["qemu-img","create","-f","qcow2"]
            if parentImage is not None:
                cmd.append("-o")
                cmd.append("backing_fmt=qcow2,backing_file=%s" % parentImage)
            cmd.append(templateImage)
            if parentImage is None:
                cmd.append("10G")
            subprocess.call(cmd)

            if parentImage is None:
                self.__format_disk(templateImage,format,driver)

            self.__extract_tarballs(destdir + "/" + imagetagid + "/template.",format,driver)
            parentImage = templateImage


    def __check_disk_format(self,format):
        supportedFormats = ['qcow2']
        if not format in supportedFormats:
            raise ValueError(["Unsupported image format %s" % format])

    def __get_image_list(self,name,destdir):
        imageparent = {}
        imagenames = {}
        imagedirs = os.listdir(destdir)
        for imagetagid in imagedirs:
            indexfile = destdir + "/" + imagetagid + "/index.json"
            if os.path.exists(indexfile):
                with open(indexfile,"r") as f:
                    index = json.load(f)
                imagenames[index["name"]] = imagetagid
            jsonfile = destdir + "/" + imagetagid + "/template.json"
            if os.path.exists(jsonfile):
                with open(jsonfile,"r") as f:
                    template = json.load(f)
                parent = template.get("parent",None)
                if parent:
                    imageparent[imagetagid] = parent
        if not name in imagenames:
            raise ValueError(["Image %s does not exist locally" %name])
        imagetagid = imagenames[name]
        imagelist = []
        while imagetagid != None:
            imagelist.append(imagetagid)
            parent = imageparent.get(imagetagid,None)
            imagetagid = parent
        return imagelist

    def __format_disk(self,disk,format,driver):
        cmd = ['virt-sandbox',
               '-c',driver,
               '--disk=file:disk_image=%s,format=%s' %(disk,format),
               '/sbin/mkfs.ext3',
               '/dev/disk/by-tag/disk_image']
        subprocess.call(cmd)

    def __extract_tarballs(self,directory,format,driver):
        tempdir = "/mnt"
        tarfile = directory + "tar.gz"
        diskfile = directory + "qcow2"
        cmd = ['virt-sandbox',
               '-c',driver,
               '-m',
               'host-image:/mnt=%s,format=%s' %(diskfile,format),
               '--',
               '/bin/tar',
               'zxvf',
               '%s' %tarfile,
               '-C',
               '/mnt']
        subprocess.call(cmd)

def debug(msg):
    sys.stderr.write(msg)

if __name__ == "sources.DockerSource":
    from __builtin__ import add_hook
    add_hook('docker',DockerSource)