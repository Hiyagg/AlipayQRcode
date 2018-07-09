#coding:utf8
import uiautomator2 as u2
import time
from config import phonelist
import threading

d = [u2.connect(i['ip']) for i in phonelist]  # 手机列表


def getqr(d, user, account, qrmoney, qrnum):
    print('账户%s正在生成二维码' % account, end='')
    print(" %s%s%s%s" % (user, account, qrmoney, qrnum))
    d.app_start('com.eg.android.AlipayGphone')
    d(text='设置金额').click()
    time.sleep(0.2)
    d.set_fastinput_ime(True)  # 切换成FastInputIME输入法
    d.send_keys(str(float(qrmoney)/100))  # adb广播输入
    time.sleep(0.2)
    d(text='添加收款理由').click()
    time.sleep(0.2)
    d.send_keys("%s%s%s%s" % (user, account, qrmoney, qrnum))  # adb广播输入
    time.sleep(0.2)
    d(text='确定').click()
    time.sleep(0.2)
    d(text='保存图片').click()
    time.sleep(0.5)
    d(text='清除金额').click()
    time.sleep(0.2)

    print('账户%s正在扫描二维码' % account)
    d.app_start('mark.qrcode')
    time.sleep(0.5)
    d(text='从图库扫描…').click()

    if account == '001':  # 三星
        time.sleep(0.2)
        d.tap(0.26, 0.32)
    elif account == '003':  # 小米
        time.sleep(0.5)
        d.tap(0.282, 0.814)
        time.sleep(0.2)
        d.tap(0.125, 0.3)
    elif account == '002':  # 中兴
        time.sleep(0.5)
        d.tap(0.26, 0.3)
    time.sleep(0.5)
    print('账户%s正在解析二维码' % account)
    url = d(resourceId="mark.qrcode:id/p").get_text()
    time.sleep(0.2)
    d.press('back')
    return user+account+qrmoney+qrnum+'    '+url


def creatbill(i, user, account):
    """
    :param i:手机编码
    :param user:商户号
    :param account:支付宝账户编号
    :return: none
    """
    print(threading.currentThread())
    t0 = time.time()
    for qrmoney in [x for x in range(10, 21) if x % 10 == 0]:  # 金额，单位分，七位数
        qrmoney = "%07d" % qrmoney
        for qrnum in range(1, 3):  # 某金额二维码编号，两位数
            qrnum = "%02d" % qrnum
            qrcode=getqr(d[i], user, account, qrmoney, qrnum)  # 生成一个二维码
            print('账户%s正在保存二维码' % account)
            with open('url%s.txt' % (user+account), 'a') as f:
                f.write(qrcode+'\n')
    print(time.time() - t0)


for i in range(1, 3):  # 三台手机
    user, account = phonelist[i]['user'], phonelist[i]['account']
    threading.Thread(target=creatbill, args=(i, user, account)).start()
print(threading.enumerate())