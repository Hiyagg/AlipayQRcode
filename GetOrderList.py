# coding:utf8
import uiautomator2 as u2
import time
import requests
import re
import hashlib
import threading
from multiprocessing import Process,Pool
import logging
import datetime
import pymysql


"""
监控支付宝到账通知，获取订单信息，记录并发送回调给服务器
"""
logging.basicConfig(level=logging.INFO,
                format='%(asctime)s %(process)d %(threadName)s %(funcName)s %(levelname)s %(message)s ',
                datefmt='%Y-%m-%d %H:%M:%S',
                filename='log.log',
                filemode='a')

info = logging.info
warning = logging.warning


class Phone(object):

    mysql = ''  # Mysql连接
    cur = ''  # 游标

    def __init__(self, ip, accountinfo):
        self.accountinfo = accountinfo
        self.orderlast = [{'billAmount': '', 'billName': '', 'timeInfo': ''}]
        self.orderlast[0]['billAmount'], self.orderlast[0]['billName'], self.orderlast[0]['timeInfo'] = self.sql_search(accountinfo)
        print(self.orderlast)
        self.ordernew = []
        self.pages = 0
        self.ct = u2.connect(ip)

    # 获取界面信息，匹配订单数据，筛选，返回新订单
    def findbill(self):
        time.sleep(0.2)
        info('Try get data')
        # 找到当前屏幕内所有的显示完整订单
        billlist = self.ct.dump_hierarchy()
        pattern = re.compile('(\\d{18,20})[\\s\\S]*?([+]\\d{1,5}\\.\\d\\d)[\\s\\S]*?(\\d\\d:\\d\\d)')  #匹配订单备注，订单金额，交易时间
        bills = pattern.findall(billlist)
        if not bills:
            warning('No new order , try open app again')  # 没有读取到订单 重新打开支付宝进入账单界面
            self.openapp(0)
            return 1

        for bill in bills:
            billname, billamount, timeinfo = bill[0], bill[1], bill[2].replace(':', '')+'00'
            billdata = {'billAmount': billamount[1:], 'billName': billname,
                        'timeInfo': '%s' % timeinfo}  # 订单格式
            #input(billdata)
            if billdata in self.ordernew:  # 如果已在本次订单列表中，则跳过该笔订单
                # input('已在本次订单列表中，则跳过该笔订单')
                continue
            elif billdata in self.orderlast:  # 如果已在上次的订单列表中，则结束读取
                # input('已在上次订单列表中，则结束')
                return 0  # 返回0，告知完毕
            else:
                #input('否则继续查找')
                self.ordernew.append(billdata)  # 否则添加到新订单列表
        info('all bills are new, continue find')
        self.pages += 1
        self.ct.swipe(0.5, 0.85, 0.5, 0.2, 0.5)
        return 1  # 上滑查看更多订单，返回1，继续获取


    def get(self):
        info('start get new order')
        flag = self.findbill()
        while flag:
            flag = self.findbill()
        info('Get complete')
        print('New order: ', self.ordernew)
        if self.ordernew:
            with open('record.txt', 'a') as f:  # 储存在本地
                f.write(str(self.ordernew)+'\n')
            self.orderlast = self.ordernew  # 记录本次的获取订单列表
        return self.ordernew

    def openapp(self, restart):
        info('Open alipay app')
        self.ct.app_stop('com.eg.android.AlipayGphone')
        self.ct.app_start('com.eg.android.AlipayGphone')
        self.ct(text='我的').click_exists(5)
        self.ct(text='账单').click_exists(5)
        if restart == 1:
            return 1

    def run(self):
        info('Start Watching')
        print(self.accountinfo, 'is running')
        while 1:
            start = 0
            restart = 0
            time.sleep(1)
            if self.ct.info['currentPackageName'] != 'com.eg.android.AlipayGphone':
                restart = self.openapp(1)
            if self.ct(text='支付宝通知').exists:
                start = 1
            if start or restart == 1:
                info('Alipay information，ready to get bills')
                print('GET F5')
                ctime = datetime.datetime.now().strftime('%Y%m%d%H%M%S')  # 当前时间
                self.ct.swipe(0.5, 0.3, 0.5, 0.6, 0.03)  # 下拉刷新账单
                self.ordernew = []  # 新订单表清零

                # 获取订单信息
                st_time = time.time()
                order = self.get()
                use_time = time.time()-st_time
                info('Delay time：%s' % use_time)
                # print(order)
                if not order:
                    print('No new order')
                    warning('No new order!!!')
                    continue
                # 发送订单线程
                info('Create new thread to send data')
                print('RETURN TOP')

                threading.Thread(target=self.send_url, args=(order, ctime)).start()

                # 返回订单顶部
                for swipe_times in range(self.pages):
                    self.ct.swipe(0.5, 0.2, 0.5, 0.85, 0.3)
                self.pages = 0
                time.sleep(1)

    @classmethod
    def send_url(cls, order, ctime):  # 发送回调
        info('Start send order data')
        print('SEND BEGIN')
        cls.host_state = 1
        # 测试接口连通性
        try:
            print('Test remote host connection')
            requests.post('http://112.74.40.81:11150/cgi-bin/v2.0/api_ali_pay_pqrcode_notify.cgi', data='123')
            print('Success, continue')
        except Exception as e:
            print('Send failed, save state')
            warning('........Failed......... , Error：%s, write 0 to db' % e)  # 尝试连接失败，订单不发送，先写0入库
            cls.host_state = 0
        # 生成订单信息
        key = '123456'
        for oneorder in order:  # 如存在多笔订单，则分别发送
            nums = len(order)-order.index(oneorder)  # 笔数
            order_id = ctime + '%02d' % nums  # 入库时订单id
            if cls.host_state == 0:
                info('for 0 , save')
                cls.sql_insert(ctime, oneorder, order_id, status='0')
                continue
            else:
                msg = 'billAmount=%s&billName=%s&timeInfo=%s' % \
                      (oneorder['billAmount'], oneorder['billName'], ctime[:8] + oneorder['timeInfo'])
                #info('Original str: %s' % msg)  # 原始串
                msg_key = msg + '&key=' + key
                md5 = hashlib.md5()
                md5.update(msg_key.encode(encoding='utf-8'))
                sign = md5.hexdigest()
                msg_send = msg + '&sign=' + sign  # 签名串
                # input(msg_send)
                info('Signed str: %s' % msg_send)
                response = requests.post('http://112.74.40.81:11150/cgi-bin/v2.0/api_ali_pay_pqrcode_notify.cgi',
                                         data=msg_send)
                recode = response.text
                print('Send success, Reply: %s' % recode)
                info('Send success, Reply: %s' % recode + ' write to db')
                if recode == 'SUCCESS':
                    cls.sql_insert(ctime, oneorder, order_id, status='1')
                else:
                    cls.sql_insert(ctime, oneorder, order_id, status='2')
                info('Save complete')
                continue
        info('ALL send over')
        print('SEND OVER')

    @classmethod
    def sql_insert(cls, ctime, oneorder, order_id, status):  # 订单入库
        info('connect mysql and insert into table')
        cls.sql_conn()
        acountinfo, billname, billamount, timeinfo = \
            oneorder['billName'][:9], oneorder['billName'], oneorder['billAmount'], oneorder['timeInfo']
        sql = "INSERT INTO `orders`.`new_table` (`acountinfo`, `billname`, `billamount`, `timeinfo`, " \
            "`ctime`, `status`,`order_id`) VALUES (%s,%s,%s,%s,%s,%s,%s);" % (acountinfo, billname, billamount, timeinfo, ctime, status, order_id)
        #input(sql)
        cls.cur.execute(sql)
        cls.mysql.commit()
        info('over , close connect')
        cls.sql_close()

    @classmethod
    def sql_search(cls, acountinfo):  # 查找最近的一笔订单记录
        info('connect mysql and search the last order')
        cls.sql_conn()
        sql = "SELECT billamount,billname,timeinfo FROM `orders`.`new_table` WHERE acountinfo=%s ORDER BY order_id DESC limit 0,5" % acountinfo
        #input(sql)
        cls.cur.execute(sql)
        order_data = cls.cur.fetchmany(1)[0]  # fetch返回元组，只要最新的一笔
        # input(order_data)
        info('over , close connect and return order')
        cls.sql_close()
        return order_data

    @classmethod
    def sql_conn(cls):  # 连接数据库
        cls.mysql = pymysql.connect(host='', port=3306, user='', passwd='', db='orders')
        cls.cur = cls.mysql.cursor()

    @classmethod
    def sql_close(cls):  # 关闭数据库连接
        cls.cur.close()
        cls.mysql.close()


if __name__ == '__main__':

    while 1:
        # ip地址及账户编号
        ip, account = '192.168.31.97', '123456002'
        ip_input = input('\n请输入ip地址:')
        account_input = input('请输入账户编号:')
        if ip_input == '' and account_input == '':
            print('未输入，使用默认值')
        else:
            ip, account = ip_input, account_input
        GG = input('ip: %s, account: %s , 输入GG继续，否则重新输入\n' % (ip, account))
        if GG == 'GG':
            break
        continue

    phone = Phone(ip, account)
    phone.run()



