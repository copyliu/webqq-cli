# -*- coding:utf-8 -*-

import urllib2, cookielib
import json
from urllib2 import BaseHandler
import random
from hashlib import md5
import gevent

GET_VCODE_URL = "http://check.ptlogin2.qq.com/check?uin=%s&appid=1003903&r=%s"

class WebqqHandler(BaseHandler):

    def http_request(self, request):
        request.add_header("Referer","http://d.web2.qq.com/proxy.html?v=20110331002&callback=2")
        return request

class WebQQException(Exception):pass

class WebQQ(object):

    def __init__(self):
        self.qq="1412089871"
        self.ptwebqq=""
        self.psessionid=""
        self.clientid=str(random.randint(1,99999999))
        self.vfwebqq=""
        self.vcode=""
        self.uin=""
        self.ckjar = cookielib.MozillaCookieJar("/tmp/cookies.txt")
        self.cookiejar = urllib2.HTTPCookieProcessor(self.ckjar)
        self.opener = urllib2.build_opener(self.cookiejar, WebqqHandler)
        self.fakeid = ""
        self.friends = None

    def getveficode(self):
        pass

    def gethashpwd(self):
        w = "alex8224"
        return md5(\
                md5(\
                    (md5(w).digest()+self.uin)\
                    ).hexdigest().upper()+self.vcode\
                  ).hexdigest().upper()

    def login1(self):
        login1url = "http://ptlogin2.qq.com/login?u="+self.qq+"&p="+self.gethashpwd()+"&verifycode="+self.vcode+"&webqq_type=10&remember_uin=1&login2qq=1&aid=1003903&u1=http%3A%2F%2Fwebqq.qq.com%2Floginproxy.html%3Flogin2qq%3D1%26webqq_type%3D10&h=1&ptredirect=0&ptlang=2052&from_ui=1&pttype=1&dumy=&fp=loginerroralert&action=1-20-8656&mibao_css=m_webqq&t=1&g=1"

        self.opener.open(login1url)
        self.ptwebqq = self.ckjar._cookies[".qq.com"]["/"]["ptwebqq"].value
        return self

    def login(self):
        response = self.opener.open(GET_VCODE_URL % (self.qq,random.random())).read()
        retcode, vcode, uin = eval(response[12:-1]) 
        if retcode !='0':
            raise WebQQException()

        self.vcode = vcode
        self.uin = uin
        return self

    def login2(self):
        login2url = "http://d.web2.qq.com/channel/login2"
        encodeparams = "r=%7B%22status%22%3A%22online%22%2C%22ptwebqq%22%3A%22"+self.ptwebqq+"%22%2C%22passwd_sig%22%3A%22%22%2C%22clientid%22%3A%22"+self.clientid+"%22%2C%22psessionid%22%3Anull%7D&clientid="+self.clientid+"&psessionid=null"
        login2request = urllib2.Request(login2url, encodeparams)
        login2request.add_header("Referer","http://d.web2.qq.com/proxy.html?v=20110331002&callback=1&id=2")
        response = json.loads(self.opener.open(login2url, encodeparams).read())
        self.vfwebqq = response["result"]["vfwebqq"]
        self.psessionid = response["result"]["psessionid"]
        self.fakeid = response["result"]["uin"]
        print "登陆成功..."
        return self

    def start(self):
        self.login().login1().login2().get_friends().poll_message()

    def get_friends(self):
        print "获取朋友列表..."
        getfriendurl = "http://s.web2.qq.com/api/get_user_friends2"
        encodeparams = "r=%7B%22h%22%3A%22hello%22%2C%22vfwebqq%22%3A%22"+self.vfwebqq+"%22%7D"
        getfriendreq = urllib2.Request(getfriendurl, encodeparams)
        getfriendreq.add_header("Referer","http://d.web2.qq.com/proxy.html?v=20110331002&callback=2")
        getfriendreq.add_header("User-Agent","Mozilla/5.0 (X11; Linux i686; rv:16.0) Gecko/20100101 Firefox/16.0")

        self.friends = json.loads(urllib2.urlopen(getfriendreq).read())
        if self.friends["retcode"]!=0:
            raise WebQQException("get_friends failed")
        return self

    def poll_message(self):
        poll_mess_url = "http://d.web2.qq.com/channel/poll2"
       
        encodeparams = "r=%7B%22clientid%22%3A%22"+self.clientid+"%22%2C%22psessionid%22%3A%22"+self.psessionid+"%22%2C%22key%22%3A0%2C%22ids%22%3A%5B%5D%7D&clientid="+self.clientid+"&psessionid="+self.psessionid
        pollreq = urllib2.Request(poll_mess_url, encodeparams)
        pollreq.add_header("Referer","http://d.web2.qq.com/proxy.html?v=20110331002&callback=1&id=3")
        pollreq.add_header("User-Agent","Mozilla/5.0 (X11; Linux i686; rv:16.0) Gecko/20100101 Firefox/16.0")

        while 1:
            try:
                response = json.loads(urllib2.urlopen(pollreq).read())
                print response
                if response["retcode"]==0:
                    result = response["result"]
                    for message in result:
                        poll_type, value = message["pll_type"], message["value"]
                        if poll_type == "buddies_status_change":
                            print "用户状态变更消息"
                        if poll_type == "message":
                            fromwho = value["reply_ip"]
                            print "收到用户发来的消息"
            except Exception, e:
                print str(e)

if __name__ == '__main__':
    qq = WebQQ()
    qq.start()
