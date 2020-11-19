# -*- coding: utf-8 -*-
"""
=============
执行融合的主程序
=============
"""
import argparse
import datetime

from self_test import check
from subgraphs import delete_old
from configparser import ConfigParser
# from multiprocessing import Pool
from gen_logger import gen_logger
import pymysql


logger = gen_logger('fuse.log', True)

parser = argparse.ArgumentParser()

parser.add_argument('--new-label', type=str, required=False, help='生成的融合图的标签')

args = parser.parse_args()
label = args.new_label
if not label:
    label = 'merge'


class NotSupportError(Exception):
    pass


if __name__ == '__main__':
    cfg = ConfigParser()

    with open('./config_files/application.cfg', encoding='utf-8') as f:
        cfg.read_file(f)
    mysql = cfg.get('mysql', 'mysql')
    conn = pymysql.connect(**eval(mysql))

    logger.info("Check the configuration file...")
    processes = check()
    logger.info("Done\n")
    logger.info("Delete old results in Neo4j...")
    delete_old(label)
    logger.info("Done\n")
    logger.info("Delete old results in MySQL...")
    now = datetime.datetime.now().strftime('%Y-%m-%d')
    conn.cursor().execute("delete from fuse_results where period = '%s'" % now)
    conn.commit()
    conn.close()
    logger.info("Done\n")

    logger.info("Start to fuse")
    from utils import fuse_root_nodes, fuse_and_create
    root_results = fuse_root_nodes()

    if root_results is None:
        logger.warning("Root nodes has no data after fused")
    else:
        logger.info("Start to fuse subgraphs...")
        if processes == 1:
            logger.info("单进程融合")
            for i in range(len(root_results)):
                fuse_and_create((label, root_results[i], i, len(root_results)))
        else:
            logger.info("多进程融合")
            raise NotSupportError("Fusing use multi processes is not supported for now.")
            # p = Pool(processes=processes)
            # for i in range(len(root_results)):
            #     p.apply_async(fuse_and_create, args=((label, root_results[i], i, len(root_results)),))
            # p.close()
            # p.join()
    logger.info("Complete fusion")
    print("融合完成")
