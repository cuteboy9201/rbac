#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@Author: Youshumin
@Date: 2019-11-12 16:55:25
@LastEditors: Youshumin
@LastEditTime: 2019-11-14 15:37:07
@Description: 认证相关...
    md5_password  密码加密
    create_token  创建token
    decode_token  解密token
    auth_middleware  检测是否登陆
    get_captcha_text 生成随机验证码
'''
import re
import hashlib
import logging
from datetime import datetime, timedelta
from functools import wraps
from oslo.util import dbObjFormatToJson
import jwt
from tornado import gen

from dblib import crud as crudmixin

LOG = logging.getLogger(__name__)

JWT_SECRET = "5A@7^bV8WGqKJIM^!h$$*jd7@KAlSw$a"
JWT_ALGORITHM = "HS256"
JWT_EXP_DELTA_SECONDS = 60 * 60 * 3
uuid_re = "^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$"


def md5_password(nickname, password):
    salt = "59E6520E-FF4D-4020-AE44-F3A20484472B"
    en_str = "%s%s%s" % (nickname, password, salt)
    return hashlib.md5(en_str.encode("utf-8")).hexdigest()


def create_token(user_id):

    payload = {
        "userId": user_id,
        "exp": datetime.utcnow() + timedelta(seconds=JWT_EXP_DELTA_SECONDS)
    }

    jwt_token = jwt.encode(payload, JWT_SECRET, JWT_ALGORITHM)

    return jwt_token


def decode_token(jwt_token):
    return jwt.decode(jwt_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def create_md_code(info, exp=60 * 5):
    '''
    @description:  生成验证码有效期5分钟
    @param {type} 
    @return: 
    '''
    payload = {"info": info, "exp": datetime.utcnow() + timedelta(seconds=exp)}
    md_code = jwt.encode(payload, JWT_SECRET, JWT_ALGORITHM)
    return md_code


def decode_md_code(md_code):
    '''
    @description: 解析登陆验证码
    @param {type} 
    @return: 
    '''
    try:
        payload = jwt.decode(md_code, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        info = payload.get("info")
    except:
        info = False
    return info


def auth_middleware():
    def login_required(func):
        @wraps(func)
        # @gen.coroutine
        def wrapper(self, *args, **kwargs):
            jwt_token = self.request.headers.get('authorization', None)
            if jwt_token:
                try:
                    jwt_token = jwt_token.split(" ")[-1]
                    payload = decode_token(jwt_token)
                except (jwt.DecodeError, jwt.ExpiredSignatureError) as e:
                    LOG.error(e)
                    self.send_fail_json(msg="Token is invalid",
                                        code=400,
                                        status=401)
                    return
                self.user_id = payload["userId"]
            else:
                self.send_fail_json(
                    msg="Login timeout please refresh and re-login",
                    code=401,
                    status=401)
                return
            return func(self, *args, **kwargs)

        return wrapper

    return login_required


def get_captcha_text(length=4):
    import random
    ALL_CHARS = '1345678abcdefhkmnpqrstuvwxyABCEFGHJKMNPQRSTUVWXY'
    selected_chars = random.sample(ALL_CHARS, k=length)
    return ''.join(selected_chars)


def PermissionCheck(func):
    '''
    @description:  权限验证装饰器
    @param {type} 
    @return: 
    '''
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            if not self.user_id:
                self.send_error(msg="没有权限")
                return
        except:
            self.send_error(msg="没有权限")
            return

        user = crudmixin.User()
        isAdmin = user.isAdmin(self.user_id)
        if isAdmin:

            return (func(self, *args, **kwargs))
        else:
            roleuser = crudmixin.RoleUser()
            roles = roleuser.getRoleIds(self.user_id)
            role_list = [item.roleId for item in roles]
            if not role_list:
                self.send_fail_json(msg="没有权限")
                return

            # 角色权限对象
            role_function = crudmixin.RoleFunction().getRoleFunctionByRoleIds(
                role_list)
            # 用户权限ID列表
            functions = [item.menuId for item in role_function]
            # 用户权限对象
            menu = crudmixin.Menu().getMenuListByIds(functions)
            # @3用户权限列表
            user_permission = [item.permission for item in menu]
            if not user_permission:
                self.send_fail_json(msg="没有权限")
                return

            # 用户接口访问权限
            userFunctionInterface = crudmixin.FunctionInterface(
            ).getFunctionInterfaceByFunctions(functions)
            userFunctionInterfaceList = [
                item.interfaceId for item in userFunctionInterface
            ]
            interfacedb = crudmixin.Interface().getByIds(
                userFunctionInterfaceList)
            dict_interface = [dbObjFormatToJson(item) for item in interfacedb]

            if not dict_interface:
                self.send_fail_json(msg="没有权限")
                return

            LOG.debug("user_perrssion: {}".format(dict_interface))

            request_path = self.request.path
            end_path = request_path.split("/")[-1]
            ret = re.match(uuid_re, end_path)
            if ret:
                start_path = "/".join(request_path.split("/")[:-1])
                request_path = "{}/:id".format(start_path)
                LOG.debug("now request path: {}".format(request_path))
            req_method = self.request.method

            LOG.debug(req_method)

            flat = False
            for item in dict_interface:
                if item["path"] == request_path and item["method"].upper(
                ) == req_method.upper():
                    LOG.debug("有权限")
                    flat = True
                    break
            if not flat:
                self.send_fail_json(msg="没有权限")
                return
            return func(self, *args, **kwargs)

    return wrapper
