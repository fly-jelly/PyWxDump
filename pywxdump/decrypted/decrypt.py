import argparse
import hmac
import hashlib
import os
from typing import Union, List
from Cryptodome.Cipher import AES

# from Crypto.Cipher import AES # 如果上面的导入失败，可以尝试使用这个

SQLITE_FILE_HEADER = "SQLite format 3\x00"  # SQLite文件头

KEY_SIZE = 32
DEFAULT_PAGESIZE = 4096
DEFAULT_ITER = 64000


# 通过密钥解密数据库
def decrypt(key: str, db_path, out_path):
    """
    通过密钥解密数据库
    :param key: 密钥 64位16进制字符串
    :param db_path:  待解密的数据库路径(必须是文件)
    :param out_path:  解密后的数据库输出路径(必须是文件)
    :return:
    """
    if not os.path.exists(db_path) or not os.path.isfile(db_path):
        return False, f"[-] db_path:'{db_path}' File not found!"
    if not os.path.exists(os.path.dirname(out_path)):
        return False, f"[-] out_path:'{out_path}' File not found!"

    if len(key) != 64:
        return False, f"[-] key:'{key}' Len Error!"

    password = bytes.fromhex(key.strip())
    with open(db_path, "rb") as file:
        blist = file.read()

    salt = blist[:16]
    byteKey = hashlib.pbkdf2_hmac("sha1", password, salt, DEFAULT_ITER, KEY_SIZE)
    first = blist[16:DEFAULT_PAGESIZE]

    mac_salt = bytes([(salt[i] ^ 58) for i in range(16)])
    mac_key = hashlib.pbkdf2_hmac("sha1", byteKey, mac_salt, 2, KEY_SIZE)
    hash_mac = hmac.new(mac_key, first[:-32], hashlib.sha1)
    hash_mac.update(b'\x01\x00\x00\x00')

    if hash_mac.digest() != first[-32:-12]:
        return False, f"[-] Key Error! (key:'{key}'; db_path:'{db_path}'; out_path:'{out_path}' )"

    newblist = [blist[i:i + DEFAULT_PAGESIZE] for i in range(DEFAULT_PAGESIZE, len(blist), DEFAULT_PAGESIZE)]

    with open(out_path, "wb") as deFile:
        deFile.write(SQLITE_FILE_HEADER.encode())
        t = AES.new(byteKey, AES.MODE_CBC, first[-48:-32])
        decrypted = t.decrypt(first[:-48])
        deFile.write(decrypted)
        deFile.write(first[-48:])

        for i in newblist:
            t = AES.new(byteKey, AES.MODE_CBC, i[-48:-32])
            decrypted = t.decrypt(i[:-48])
            deFile.write(decrypted)
            deFile.write(i[-48:])
    return True, [db_path, out_path, key]


def batch_decrypt(key: str, db_path: Union[str, List[str]], out_path: str, is_logging: bool = False):
    if not isinstance(key, str) or not isinstance(out_path, str) or not os.path.exists(out_path) or len(key) != 64:
        error = f"[-] (key:'{key}' or out_path:'{out_path}') Error!"
        if is_logging: print(error)
        return False, error

    process_list = []

    if isinstance(db_path, str):
        if not os.path.exists(db_path):
            error = f"[-] db_path:'{db_path}' not found!"
            if is_logging: print(error)
            return False, error

        if os.path.isfile(db_path):
            inpath = db_path
            outpath = os.path.join(out_path, 'de_' + os.path.basename(db_path))
            process_list.append([key, inpath, outpath])

        elif os.path.isdir(db_path):
            for root, dirs, files in os.walk(db_path):
                for file in files:
                    inpath = os.path.join(root, file)
                    rel = os.path.relpath(root, db_path)
                    outpath = os.path.join(out_path, rel, 'de_' + file)

                    if not os.path.exists(os.path.dirname(outpath)):
                        os.makedirs(os.path.dirname(outpath))
                    process_list.append([key, inpath, outpath])
        else:
            error = f"[-] db_path:'{db_path}' Error "
            if is_logging: print(error)
            return False, error

    elif isinstance(db_path, list):
        rt_path = os.path.commonprefix(db_path)
        if not os.path.exists(rt_path):
            rt_path = os.path.dirname(rt_path)

        for inpath in db_path:
            if not os.path.exists(inpath):
                erreor = f"[-] db_path:'{db_path}' not found!"
                if is_logging: print(erreor)
                return False, erreor

            inpath = os.path.normpath(inpath)
            rel = os.path.relpath(os.path.dirname(inpath), rt_path)
            outpath = os.path.join(out_path, rel, 'de_' + os.path.basename(inpath))
            if not os.path.exists(os.path.dirname(outpath)):
                os.makedirs(os.path.dirname(outpath))
            process_list.append([key, inpath, outpath])
    else:
        error = f"[-] db_path:'{db_path}' Error "
        if is_logging: print(error)
        return False, error

    result = []
    for i in process_list:
        result.append(decrypt(*i))  # 解密

    # 删除空文件夹
    for root, dirs, files in os.walk(out_path, topdown=False):
        for dir in dirs:
            if not os.listdir(os.path.join(root, dir)):
                os.rmdir(os.path.join(root, dir))

    if is_logging:
        print("=" * 32)
        success_count = 0
        fail_count = 0
        for code, ret in result:
            if code == False:
                print(ret)
                fail_count += 1
            else:
                print(f'[+] "{ret[0]}" -> "{ret[1]}"')
                success_count += 1
        print("-" * 32)
        print(f"[+] 共 {len(result)} 个文件, 成功 {success_count} 个, 失败 {fail_count} 个")
        print("=" * 32)
    return True, result


if __name__ == '__main__':
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser()
    parser.add_argument("-k", "--key", type=str, help="密钥", required=True)
    parser.add_argument("-i", "--db_path", type=str, help="数据库路径(目录or文件)", required=True)
    parser.add_argument("-o", "--out_path", type=str,
                        help="输出路径(必须是目录),输出文件为 out_path/de_{original_name}", required=True)

    # 解析命令行参数
    args = parser.parse_args()

    # 从命令行参数获取值
    key = args.key
    db_path = args.db_path
    out_path = args.out_path

    # 调用 decrypt 函数，并传入参数
    result = batch_decrypt(key, db_path, out_path)
    for i in result:
        if isinstance(i, str):
            print(i)
        else:
            print(f'[+] "{i[1]}" -> "{i[2]}"')
