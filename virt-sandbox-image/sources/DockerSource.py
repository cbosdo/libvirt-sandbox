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

def debug(msg):
    sys.stderr.write(msg)

if __name__ == "sources.DockerSource":
    from __builtin__ import add_hook
    add_hook('docker',DockerSource)
