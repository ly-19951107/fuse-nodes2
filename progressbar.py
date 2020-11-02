# -*- coding: utf-8 -*-
import sqlite3
import time

db_filename = 'progressbar.db'


class ProgressBar:
    def __init__(self, bar_name):
        assert isinstance(bar_name, str), '必须传入字符型的进度条名称！'
        self.table = bar_name
        self.conn = sqlite3.connect(db_filename, check_same_thread=False)

    def create(self):
        """创建一个进度条，即在数据库中创建对应表。

        如果在不同的脚本中查询进度条，则不应该调用本方法。本方法会导致同名进度条的进度数据消失，
        在程序被非正常终止时可以利用本方法进行重置。
        """
        try:
            self.conn.execute(f'''
                create table {self.table} (
                    id integer primary key autoincrement not null,
                    progress float,
                    insert_time time );
                ''')
        except sqlite3.OperationalError:
            # 该进度条对应的表已经存在，清空其所有内容，只保留表结构
            print("WARNING: 同名进度条已存在，将被覆盖！")
            self.conn.execute(f"delete from {self.table}")
            self.conn.execute(f"delete from sqlite_sequence where name='{self.table}'")
        self.conn.commit()

    def set(self, value: float):
        """将进度值写入对应表"""
        self.conn.execute(f"insert into {self.table} (progress, insert_time)values ({value}, "
                          f"'{time.strftime('%Y-%m-%d %H-%M-%S')}')")
        self.conn.commit()

    def get(self):
        """获取指定进度条的当前进度"""
        cr = self.conn.cursor()
        cr.execute(f"select progress from {self.table} where id=(select max(id) from "
                   f"{self.table})")
        try:
            progress = cr.fetchone()[0]
        except TypeError:  # 刚创建时，进度表中并无数据
            progress = 0.0
        return progress
