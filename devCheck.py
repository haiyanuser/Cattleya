#!/root/abc/venv/bin/python3
# -*- coding: UTF-8 -*-

import os
import sys
import time
import pandas
import threading
from netmiko import ConnectHandler
from progressbar import ProgressBar, Percentage, Bar


info_file = os.path.join(os.getcwd(), 'info.xlsx')  # 给定info文件
current_time = time.strftime('%Y.%m.%d', time.localtime())  # 读取当前日期
LOCK = threading.Lock()  # 线程锁实例化
POOL = threading.BoundedSemaphore(100)  # 最大线程控制,当前100个线程可以同时运行


def get_devices_info(info_file):  # 获取info文件中的设备登录信息
    try:
        devices_dataframe = pandas.read_excel(info_file, sheet_name=0, dtype=str, keep_default_na=False)
        # 读取Excel文件第一张工作表的数据生成DataFrame
    except FileNotFoundError:  # 如果没有配置info文件或info文件名错误
        print(f'\n没有找到info文件!\n')  # 代表没有找到info文件或info文件名错误
        for i2 in range(5, -1, -1):  # 等待5秒退出程序,为工程师留有充分的时间,查看CMD中的输出信息
            if i2 > 0:
                print(f'\r程序将在 {i2} 秒后退出...', end='')
                time.sleep(1)
            else:
                print(f'\r程序已退出!', end='')
        sys.exit(1)  # 异常退出
    else:
        devices_dict = devices_dataframe.to_dict('records')  # 将DataFrame转换成字典
        devices_dict = [device for device in devices_dict if device.get('device_type')]  # 过滤空行
        return devices_dict


def get_cmds_info(info_file):  # 获取info文件中的巡检命令
    try:
        cmds_dataframe = pandas.read_excel(info_file, sheet_name=1, dtype=str)
        # 读取Excel文件第二张工作表的数据生成DataFrame
    except ValueError:  # 捕获异常信息
        print(f'\ninfo文件缺失子表格信息!\n')  # 代表info文件缺失子表格信息
        for i2 in range(5, -1, -1):  # 等待5秒退出程序,为工程师留有充分的时间,查看CMD中的输出信息
            if i2 > 0:
                print(f'\r程序将在 {i2} 秒后退出...', end='')
                time.sleep(1)
            else:
                print(f'\r程序已退出!', end='')
        sys.exit(1)  # 异常退出
    else:
        cmds_dict = cmds_dataframe.dropna(axis=0, how='all').to_dict('list')  # 删除所有值均为 NaN 的行
        cmds_dict = {key: value for key, value in cmds_dict.items() if all(value)}  # 过滤空行
        return cmds_dict


def inspection(login_info, cmds_list, progress_bar):
    # 使用传入的设备登录信息和巡检命令,登录设备依次输入巡检命令,如果设备登录出现异常,生成01log文件记录。
    ssh = None  # 初始化ssh对象

    try:  # 尝试登录设备
        ssh = ConnectHandler(**login_info)  # 使用设备登录信息,SSH登录设备
        ssh.enable()  # 进入设备Enable模式
    except Exception as ssh_error:  # 登录设备出现异常
        with LOCK:  # 线程锁
            error_name = type(ssh_error).__name__  # 获取异常名称
            if error_name == 'AttributeError':  # 异常名称为：AttributeError
                error_msg = f'设备 {login_info["host"]} 缺少设备管理地址!'  # CMD输出提示信息
            elif error_name == 'NetmikoTimeoutException':
                error_msg = f'设备 {login_info["host"]} 管理地址或端口不可达!'
            elif error_name == 'NetmikoAuthenticationException':
                error_msg = f'设备 {login_info["host"]} 用户名或密码认证失败!'
            elif error_name == 'ValueError':
                error_msg = f'设备 {login_info["host"]} Enable密码认证失败!'
            elif error_name == 'TimeoutError':
                error_msg = f'设备 {login_info["host"]} Telnet连接超时!'
            elif error_name == 'ReadTimeout':
                error_msg = f'设备 {login_info["host"]} Enable密码认证失败!'
            elif error_name == 'ConnectionRefusedError':
                error_msg = f'设备 {login_info["host"]} 目标设备拒绝了连接请求!'
            else:
                error_msg = f'设备 {login_info["host"]} 发生了未知错误：{ssh_error}'
            print(error_msg)  # CMD输出提示信息
            with open(os.path.join(os.getcwd(), current_time, '01log.log'), 'a', encoding='utf-8') as log:
                log.write(error_msg + '\n')  # 记录到log文件
    else:  # 如果登录正常，开始巡检
        with open(os.path.join(os.getcwd(), current_time, login_info['host'] + '_' + login_info['ip'] + '.log'), 'w', encoding='utf-8') as device_log_file:
            for cmd in cmds_list:  # 遍历巡检命令列表
                if isinstance(cmd, str):  # 判断读取的命令是否为字符串
                    device_log_file.write('#' * 20 + ' ' + cmd + ' ' + '#' * 20 + '\n\n')  # 写入当前巡检命令分行符，至巡检信息记录文件
                    show = ssh.send_command(cmd, read_timeout=30)  # 执行当前巡检命令,并获取结果,最长等待30s
                    device_log_file.write(show + '\n\n')  # 写入当前巡检命令的结果，至巡检信息记录文件
                    progress_bar.update(1)  # 更新进度条
            progress_bar.finish()  # 关闭进度条
    finally:  # 最后结束SSH连接释放线程
        if ssh is not None:  # 判断ssh对象是否被正确赋值,赋值成功不为None,即SSH连接已建立,需要关闭连接
            ssh.disconnect()  # 关闭SSH连接
        POOL.release()  # 最大线程限制，释放一个线程


def ready_go():
    t1 = time.time()  # 程序执行计时起始点
    threading_count = []  # 创建一个线程列表，准备存放所有线程
    devices_info = get_devices_info(info_file)  # 读取所有设备的登录信息
    cmds_info = get_cmds_info(info_file)  # 读取所有设备类型的巡检命令

    print(f'\n巡检开始...',flush=True)  # 提示巡检开始
    print(f'\n' + '>' * 85 + '\n',flush=True)  # 打印一行“>”，隔开巡检提示信息

    if not os.path.exists(current_time):  # 判断是否存在有同日期的文件夹（判断当天是否执行过巡检）
        os.makedirs(current_time)  # 如果没有，创建当天日期文件夹
    else:  # 如果有
        try:  # 尝试删除记录巡检设备异常的记录文件,即01log文件
            os.remove(os.path.join(os.getcwd(), current_time, '01log.log'))  # 删除01log文件
        except FileNotFoundError:  # 如果没有01log文件（之前执行巡检没有发生异常）
            pass  # 跳过，不做处理

    for device_info in devices_info:
        # 获取当前设备类型对应的命令列表，如果不存在则为空列表
        cmds_list = cmds_info.get(device_info['device_type'], [])  
        temp = cmds_info[device_info['device_type']]
        count = sum(1 for x in temp if str(x) != 'nan')  # 统计非空命令的数量
        progress_bar = ProgressBar(widgets=[device_info['host'] + ' ' + device_info['ip'] + ' ', Bar(), Percentage()], maxval=count).start()

        # 创建线程并执行巡检,将进度条对象作为参数传递给inspection函数
        pre_device = threading.Thread(target=inspection, args=(device_info, cmds_list, progress_bar))
        threading_count.append(pre_device)
        POOL.acquire()
        pre_device.start()

    for i in threading_count:  # 遍历所有创建的线程
        i.join()  # 等待所有线程的结束
    try:  # 尝试打开01log文件
        with open(os.path.join(os.getcwd(), current_time, '01log.log'), 'r', encoding='utf-8') as log_file:
            file_lines = len(log_file.readlines())  # 读取01log文件共有多少行(有多少行，代表出现了多少个设备登录异常）
    except FileNotFoundError:  # 如果找不到01log文件
        file_lines = 0  # 证明本次巡检没有出现巡检异常情况
    t2 = time.time()  # 程序执行计时结束点
    # 循环结束后，打印巡检结果的路径

    print(f'\n' + '<' * 85 + '\n')  # 打印一行“<”，隔开巡检报告信息
    print(f'巡检完成，共巡检 {len(threading_count)} 台设备，{file_lines} 台异常，共用时 {round(t2 - t1, 1)} 秒。\n')  # 打印巡检报告

if __name__ == '__main__':
    ready_go()