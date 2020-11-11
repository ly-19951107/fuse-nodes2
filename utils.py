"""
@Time   : 2020/6/23 3:18 \u4e0b\u5348
@Author : sunjiawei
@E-mail : j.w.sun1992@gmail.com

Functions used for distributed fuse.
"""
from configparser import ConfigParser

import datetime
import numpy as np
import pymysql
from py2neo import Graph

from gen_logger import gen_logger
from subgraphs import create_subgraph
from text_sim_utils import sims

logger = gen_logger('fuse.log', 1)
logger.info('Get the necessary information...')
cfg = ConfigParser()
with open('./config_files/application.cfg', encoding='utf-8') as (f):
    cfg.read_file(f)
neo4j_url = cfg.get('neo4j', 'url')
auth = eval(cfg.get('neo4j', 'auth'))
mysql = cfg.get('mysql', 'mysql')
THRESHOLD = cfg.getfloat('threshold', 'threshold')
with open('./config_files/neo4j-structure.cfg', encoding='utf-8') as (f):
    cfg.read_file(f)
cms, pms, gis = cfg.get('system_label', 'cms'), cfg.get('system_label', 'pms'), cfg.get(
    'system_label', 'gis')
fused_entities = cfg.get('fuse', 'entities').split(',')
if list(map(len, (cms, pms, gis))).count(0) == 1:
    if not gis:
        flag = 'cp'
        logger.info('will merge cms and pms')
    else:
        if not pms:
            flag = 'cg'
            logger.info('will merge cms and gis')
        else:
            flag = 'pg'
            logger.info('will merge pms and gis')
else:
    flag = 'all'
    logger.info('Three systems will be merged')
cms_entities = cfg.get('cms', 'entities').split(',')
cms_rel = cfg.get('cms', 'relationships').split(',')
cms_pros = cfg.get('cms', 'properties').split('&')
pms_entities = cfg.get('pms', 'entities').split(',')
pms_rel = cfg.get('pms', 'relationships').split(',')
pms_pros = cfg.get('pms', 'properties').split('&')
gis_entities = cfg.get('gis', 'entities').split(',')
gis_rel = cfg.get('gis', 'relationships').split(',')
gis_pros = cfg.get('gis', 'properties').split('&')
weight = cfg.get('weight', 'weight').split('&')
logger.info('Done')


def fuse_and_create(args):
    """融合非根节点以外的节点，并创建新图"""
    label, res, cur, tot = args  # 新图的标签、父节点融合结果、当前第几个、一共多少个
    logger.info(f'''Process:{(cur + 1)}/{tot}''')
    children = fuse_other_nodes(1, res)
    sub_graph = {'val': res, 'children': children}
    logger.info('  Save the fusion result to mysql...')
    save_to_mysql(sub_graph)
    logger.info('  Complete')
    logger.info('  Create subgraph...')
    create_subgraph(label, sub_graph)
    logger.info('  Complete')


def fuse_root_nodes():
    """融合配置文件中的第一级实体（根节点）"""
    ce, pe, ge = cms_entities[0], pms_entities[0], gis_entities[0]
    cp, pp, gp = get_property(0)
    w = eval(weight[0])
    logger.info('Get root node data...')
    cms_data = get_root_data(cms, ce, cp, w)
    pms_data = get_root_data(pms, pe, pp, w)
    gis_data = get_root_data(gis, ge, gp, w)
    logger.info('Complete')
    res = validate_data_and_fuse(0, cms_data, pms_data, gis_data)
    logger.info('The root nodes fusion is complete')
    return res


def fuse_other_nodes(start_index, root_result):
    """根据根节点的融合结果，通过递归调用的方式，融合其下面所有的节点。
    
    Args:
        start_index(int): 第几级的实体
        root_result(list): 父节点的融合结果
    
    Returns:
    
    """
    graph = Graph(neo4j_url, auth=auth)
    result_dict = {}
    i = start_index
    cp, pp, gp = get_property(i)
    w = eval(weight[i])

    def func(cms_ent, pms_ent, gis_ent):
        if root_result.count(None) == 0:  # 父节点都有数据，查找对应子节点的数据
            cms_data = get_data(graph, root_result[0], cms, 'cms', cms_ent, cp, w, i)
            pms_data = get_data(graph, root_result[1], pms, 'pms', pms_ent, pp, w, i)
            gis_data = get_data(graph, root_result[2], gis, 'gis', gis_ent, gp, w, i)
        else:
            if root_result.count(None) == 1:  # 父节点只有2个系统有数据，查找对应子节点的数据
                if root_result[0] is None:
                    cms_data = []
                    pms_data = get_data(graph, root_result[1], pms, 'pms',
                                        pms_ent, cp, w, i)
                    gis_data = get_data(graph, root_result[2], gis, 'gis',
                                        gis_ent, gp, w, i)
                else:
                    if root_result[1] is None:
                        pms_data = []
                        cms_data = get_data(graph, root_result[0], cms, 'cms',
                                            cms_ent, cp, w, i)
                        gis_data = get_data(graph, root_result[2], gis, 'gis',
                                            gis_ent, gp, w, i)
                    else:
                        gis_data = []
                        cms_data = get_data(graph, root_result[0], cms, 'cms',
                                            cms_ent, cp, w, i)
                        pms_data = get_data(graph, root_result[1], pms, 'pms',
                                            pms_ent, pp, w, i)
            else:  # 父节点只有1个系统有数据，查找对应子节点的数据
                if root_result[0] is not None:
                    pms_data, gis_data = [], []
                    cms_data = get_data(graph, root_result[0], cms, 'cms',
                                        cms_ent, cp, w, i)
                elif root_result[1] is not None:
                    cms_data, gis_data = [], []
                    pms_data = get_data(graph, root_result[1], pms, 'pms',
                                        pms_ent, pp, w, i)
                else:
                    cms_data, pms_data = [], []
                    gis_data = get_data(graph, root_result[2], gis, 'gis',
                                        gis_ent, gp, w, i)

        _res = validate_data_and_fuse(i, cms_data, pms_data, gis_data)
        return _res

    if i == 1:
        ce, pe, ge = cms_entities[i], pms_entities[i], gis_entities[i]
        res = func(ce, pe, ge)
        if res is None:
            return {}
        start_index += 1
        for j in range(len(res)):
            result_dict[j] = {'val': res[j],
                              'children': fuse_other_nodes(start_index, res[j])}
    else:
        ces, pes, ges = cms_entities[i], pms_entities[i], gis_entities[i]
        ces = ces.split('&')
        pes = pes.split('&')
        ges = ges.split('&')
        counts = 0
        for k in range(2):
            ce, pe, ge = ces[k], pes[k], ges[k]
            res = func(ce, pe, ge)
            if res is None:
                continue
            if k == 0:
                counts = len(res)
            for j in range(len(res)):
                result_dict[k * counts + j] = {'val': res[j],
                                               'children': {}}

    return result_dict


def get_property(i):
    """Get all properties that are used to calculate similarity from
    `./config_files/neo4j-structure.cfg`. In order to distinguish TEXT property and
    ENUM property, using a nested list to store them.
    
    Args:
        i(int): Number of entity labels
    
    Returns: Tuple of lists of lists
    
    """
    cms_ = eval(cms_pros[i])
    pms_ = eval(pms_pros[i])
    gis_ = eval(gis_pros[i])
    cms_list = [
        cms_['TEXT'], cms_['ENUM']]
    pms_list = [pms_['TEXT'], pms_['ENUM']]
    gis_list = [gis_['TEXT'], gis_['ENUM']]
    return cms_list, pms_list, gis_list


def get_root_data(sys, ent, prop, w):
    """从图数据库中获取根节点（第一级实体）的数据。
    
    只有`prop`中的属性和节点本身的`id`属性才会被抽取出来。在后续的计算中，`id`将被用来追溯到最初的节点。

    对于文本类属性，在抽取得到的属性名称后面会添加`TEXT_的前缀；对于枚举类属性，在抽取得到的属性名称后面会
    添加`ENUM_`的前缀。

    Args:
        sys(str): 系统的标签
        ent(str): 实体的标签啊
        prop(list): 属性的列表（嵌套结构）
        w(dict): 权重
    
    Returns:
        由字典组成的列表，每个字典代表一个图数据库中的节点。
    
    """
    graph = Graph(neo4j_url, auth=auth)
    count = 1
    cypher = f'''match (n:{sys}:{ent}) return id(n) as id_, n.'''
    for i in range(len(prop[0])):
        cypher += prop[0][i] + f''' as `TEXT_{count}_{(w['TEXT'][i])}`, '''
        count += 1

    for i in range(len(prop[1])):
        cypher += prop[1][i] + f''' as `ENUM_{count}_{(w['ENUM'][i])}`, '''
        count += 1

    cypher = cypher[:-2]
    data = graph.run(cypher).data()
    return data


def get_data(graph_, father, sys, sys_type, ent, prop, w, i):
    """从图数据库中获取数据。
    
    Args:
        graph_: `neo4j.Graph`对象
        father(str): 父节点的id
        sys(str): 系统标签
        sys_type(str): 系统类型，取值为'cms', 'pms' 或 'gis'
        ent(str): 实体标签
        prop(list): 待抽取属性的嵌套列表
        w(dict): 权重
        i(int): 关系的数量
    
    Returns:
        由字典组成的列表，每个字典代表一个图数据库中的节点。
    """
    if sys_type == 'cms':
        rel = cms_rel[i - 1][1:][:-1]
    elif sys_type == 'pms':
        rel = pms_rel[i - 1][1:][:-1]
    else:
        rel = gis_rel[i - 1][1:][:-1]
    count = 1
    #
    # 测试数据中见有实体1到实体2有多条关系的情况，暂不明确真实数据是否如此，因此这里对此进行去重限制
    #
    cypher = f'match(m){rel}(n:{sys}:{ent}) where id(m)={father} ' \
             f'return distinct id(n) as id_, n.'
    for i in range(len(prop[0])):
        cypher += prop[0][i] + f" as `TEXT_{count}_{(w['TEXT'][i])}`, "
        count += 1

    for i in range(len(prop[1])):
        cypher += prop[1][i] + f" as `ENUM_{count}_{(w['ENUM'][i])}`, "
        count += 1

    cypher = cypher[:-2]
    data = graph_.run(cypher).data()
    return data


def validate_data_and_fuse(i, cms_data, pms_data, gis_data):
    """根据获取到的数据判断各个系统真实的数据情况，在符合融合条件（至少有两个系统有数据）时，
    调用`compute_sim_and_combine`
    
    Args:
        i(int): 待融合实体的级别，用于生成更加好看的日志
        cms_data(list[dict]): 字典组成的列表
        pms_data(list[dict]): 字典组成的列表
        gis_data(list[dict]): 字典组成的列表
    
    Returns:
        None或者`compute_sim_and_combine`的输出
    """
    if not cms_data:
        logger.debug(f'''{('  ' * i)}cms system has no data''')
        cms_data = None
    if not pms_data:
        logger.debug(f'''{('  ' * i)}pms system has no data''')
        pms_data = None
    if not gis_data:
        logger.debug(f'''{('  ' * i)}gis system has no data''')
        gis_data = None
    none_counts = sum(map(lambda x: x is None, (cms_data, pms_data, gis_data)))
    if none_counts == 3:
        logger.debug(f'''{('  ' * i)}all system has no data''')
        return
    else:
        return compute_sim_and_combine(i, none_counts, cms_data, pms_data, gis_data)


def compute_sim_and_combine(i, none_counts, cms_data=None, pms_data=None, gis_data=None):
    """对于给定的各个系统的数据，计算相似度矩阵以得到最相似的实体对，然后将这些实体对的id组和成一个嵌套列表。

    Args:
        i(int): 待融合实体的级别，用于生成更加好看的日志
        none_counts(int): 0、1或2，无数据的系统的个数
        cms_data(list[dict]): cms系统的数据
        pms_data(list[dict]): cms系统的数据
        gis_data(list[dict]): cms系统的数据
    
    Returns:
    
    """
    computer = Computation(THRESHOLD)
    if none_counts == 1:
        if not cms_data:
            logger.warning(f'''{('  ' * i)}Calculate the similarity 
of two systems (pms, gis)''')
            res = computer.compute(pms_data, gis_data)
            logger.info(f'''{('  ' * i)}Complete''')
            if res is None:
                logger.warning(f'''{('  ' * i)}No similar entities''')
                return res
            logger.info(f'''{('  ' * i)}Combined the entities'id...''')
            for i_ in res:
                i_.insert(0, None)
                if i_[1] is not None:
                    i_[1] = pms_data[i_[1]]['id_']
                if i_[2] is not None:
                    i_[2] = gis_data[i_[2]]['id_']

            logger.info(f'''{('  ' * i)}Complete''')
            return res
        if not pms_data:
            logger.warning(f"{('  ' * i)}Calculate the similarity "
                           f"of two systems (cms, gis)")
            res = computer.compute(cms_data, gis_data)
            logger.info(f'''{('  ' * i)}Complete''')
            if res is None:
                logger.warning(f'''{('  ' * i)}No similar entities''')
                return res
            logger.info(f'''{('  ' * i)}Combined the entities'id...''')
            for i_ in res:
                i_.insert(1, None)
                if i_[0] is not None:
                    i_[0] = cms_data[i_[0]]['id_']
                if i_[2] is not None:
                    i_[2] = gis_data[i_[2]]['id_']

            logger.info(f'''{('  ' * i)}Complete''')
            return res
        logger.warning(f"{('  ' * i)}Calculate the similarity of two systems (cms, pms)")
        res = computer.compute(cms_data, pms_data)
        logger.info(f'''{('  ' * i)}Complete''')
        if res is None:
            logger.warning(f'''{('  ' * i)}No similar entities''')
            return res
        logger.info(f'''{('  ' * i)}Combined the entities'id...''')
        for i_ in res:
            i_.insert(2, None)
            if i_[0] is not None:
                i_[0] = cms_data[i_[0]]['id_']
            if i_[1] is not None:
                i_[1] = pms_data[i_[1]]['id_']

        logger.info('Complete')
        return res
    elif none_counts == 2:
        logger.warning(f'''{('  ' * i)}Only one system has data''')
        res = []
        if cms_data is not None:
            for i in cms_data:
                res.append([i['id_'], None, None])

        if pms_data is not None:
            for i in pms_data:
                res.append([None, i['id_'], None])

        if gis_data is not None:
            for i in gis_data:
                res.append([None, None, i['id_']])

        return res
    logger.info(f'''{('  ' * i)}Start calculating similarity (three systems)...''')
    res1 = computer.compute(cms_data, pms_data)
    res2 = computer.compute(cms_data, gis_data)
    res3 = computer.compute(pms_data, gis_data)
    logger.info(f'''{('  ' * i)}Complete''')
    logger.info(f'''{('  ' * i)}Combined the entities'id...''')
    res = []
    for j in res1:
        if j.count(None) == 0:
            cms_id, pms_id = cms_data[j[0]]['id_'], pms_data[j[1]]['id_']
            for k in res2:
                if k[0] is not None:
                    if cms_id == cms_data[k[0]]['id_']:
                        gis_id = gis_data[k[1]]['id_'] if k[1] is not None else None
                        res.append([cms_id, pms_id, gis_id])

        else:
            if j[0] is None:
                pms_id = pms_data[j[1]]['id_']
                for k in res3:
                    if k[0] is not None:
                        if pms_id == pms_data[k[0]]['id_']:
                            gis_id = gis_data[k[1]]['id_'] if k[1] is not None else None
                            res.append([None, pms_id, gis_id])

            else:
                cms_id = cms_data[j[0]]['id_']
                for k in res2:
                    if k[0] is not None:
                        if cms_id == cms_data[k[0]]['id_']:
                            gis_id = gis_data[k[1]]['id_'] if k[1] is not None else None
                            res.append([cms_id, None, gis_id])

    logger.info(f'''{('  ' * i)}Complete''')
    return res


def save_to_mysql(sub_graph):
    """将融合结果存入mysql"""
    now = datetime.datetime.now().strftime('%Y-%m-%d')
    conn = pymysql.connect(**eval(mysql))

    g = Graph(neo4j_url, auth=auth)

    sql = f'''insert into fuse_results(period, cms_id, pms_id, 
          gis_id, city_code, county_code, 
          gds_code, sys_type, equip_type) values 
          ('{now}', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s')'''

    def func(i, graph):
        if i == 0:
            args = combine_args(graph['val'])
            args.append(fused_entities[i])
            with conn.cursor() as (cr):
                cr.execute(sql % tuple(args))
        else:
            for j in graph:
                args = combine_args(graph[j]['val'])
                args.append(fused_entities[i])
                with conn.cursor() as (cr):
                    cr.execute(sql % tuple(args))
                child = graph[j]['children']
                if child is not {}:
                    func(i + 1, child)

    def combine_args(nodes):
        args = []
        _check = []
        city_code, county_code, gds_code = ('', '', '')
        for i in range(len(nodes)):
            if nodes[i] is not None:
                _check.append(1)
                data = g.run(
                    f'''match(n) where id(n)={(nodes[i])} return n.cityCode as city_code, 
                    n.mRID as mrid, n.countyCode as county_code, 
                    n.gdsCode as gds_code''').data()
                if data:
                    city_code = data[0]['city_code'] if data[0]['city_code'] else ''
                    county_code = data[0]['county_code'] if data[0]['county_code'] else ''
                    gds_code = data[0]['gds_code'] if data[0]['gds_code'] else ''
                    args.append(data[0]['mrid'])
            else:
                _check.append(0)
                args.append('')

        args.extend([city_code, county_code, gds_code])
        if _check == [1, 1, 1]:
            args.append('yx-pms-gis')
        if _check == [1, 0, 0]:
            args.append('yx')
        if _check == [1, 0, 1]:
            args.append('yx-gis')
        if _check == [1, 1, 0]:
            args.append('yx-pms')
        if _check == [0, 1, 1]:
            args.append('pms-gis')
        if _check == [0, 1, 0]:
            args.append('pms')
        if _check == [0, 0, 1]:
            args.append('gis')
        return args

    func(0, sub_graph)
    func(1, sub_graph['children'])
    conn.commit()


class Computation:
    """用于计算两个节点列表相似度的类"""

    def __init__(self, thresh=0.75):
        """相似度判定阈值，默认为0.75"""
        self.thresh = thresh
        self.match_res = []
        self.x = []
        self.y = []

    def compute(self, data1, data2):
        """主函数。
        
        Args:
            data1(list[dict]): 节点列表
            data2(list[dict]): 节点列表
        
        Returns:
            None或者融合结果列表。
        
        """
        if self.match_res:
            self.match_res = []
        if self.x:
            self.x = []
        if self.y:
            self.y = []
        sim = np.zeros(shape=(len(data1), len(data2)), dtype=np.float16)
        num = len(data2) - int(len(data2) % 4)
        for i in range(len(data1)):
            for j in range(int(num // 4)):
                j = j * 4
                sim[(i, j)] = self.__compute(data1[i], data2[j])
                sim[(i, j + 1)] = self.__compute(data1[i], data2[j + 1])
                sim[(i, j + 2)] = self.__compute(data1[i], data2[j + 2])
                sim[(i, j + 3)] = self.__compute(data1[i], data2[j + 3])
                continue
            if len(data2) > num:
                for k in range(num, len(data2)):
                    sim[(i, k)] = self.__compute(data1[i], data2[k])
        return self.__matching(sim)

    @staticmethod
    def __compute(dict1, dict2) -> float:
        """获取字典中的数据并计算相似度。
        
        Args:
            dict1(dict): 节点字典
            dict2(dict): 节点字典
        
        Returns:
            相似度的值
        """
        sim = 0.0
        for k in dict1:
            if k == 'id_':
                continue
            else:
                w = float(k.split('_')[-1])
                if k.startswith('TEXT'):
                    sim += w * sims(dict1[k], dict2[k])
                elif dict1[k] == dict2[k]:
                    sim += w
                    continue
        return sim

    def __matching(self, sim_matrix):
        """在调用`self.__match`之后，在横向或者纵向上可能遗留下一些非0值，对这些值
        进行处理。

        只处理基准表对应的数据，以保证基准表中所有的节点都被计算完成。

        Args:
            sim_matrix: 相似度矩阵

        Returns: 嵌套的列表

        """
        self.__match(sim_matrix)
        if not self.match_res:
            return
        else:
            for i in range(sim_matrix.shape[0]):
                if i not in self.x:
                    self.match_res.append([i, None])

            for j in range(sim_matrix.shape[1]):
                if j not in self.y:
                    self.match_res.append([None, j])

            return self.match_res

    def __match(self, sim_matrix):
        """利用了递归的方法，根据相似度矩阵，计算最相似的实体对。

        注意，`numpy.array.argmax()`只返回最大值的第一个索引，如果最大值的个数不为1时，这个机制可能会带来
        问题。

        Args:
            sim_matrix: 相似度矩阵

        Returns: None或嵌套的列表
        
        """
        if np.sum(sim_matrix, dtype=np.float64) == 0:
            return

        arg0 = sim_matrix.argmax(axis=0)  # 每一列的最大值的位置
        arg1 = sim_matrix.argmax(axis=1)  # 每一行的最大值的位置
        for i in range(len(arg0)):  # 按列遍历
            if i in self.y or arg0[i] in self.x:  # 已经计算
                continue  # 跳过
            if sim_matrix[(arg0[i], i)] < self.thresh:  # i列的最大值小于阈值
                sim_matrix[:, i] = 0  # 整列设置为0
                # if [None, i] not in self.match_res:  # 如果该匹配对不在结果列表中
                #     self.match_res.append([None, i])  # 追加匹配对到结果列表中
                #     self.y.append(i)  # 追加到已计算的y值列表
            else:  # i列的最大值大于等于阈值
                if arg1[arg0[i]] == i:  # 第i列的最大值刚好也是该值所处行的最大值
                    self.match_res.append([arg0[i], i])  # 将该匹配对追加到结果列表中
                    sim_matrix[:, i] = 0  # 整列设置为0
                    sim_matrix[arg0[i]] = 0  # 整行设置为0
                    self.x.append(arg0[i])  # 追加到已计算的x值列表
                    self.y.append(i)  # 追加到已计算的y值列表
        self.__match(sim_matrix)
