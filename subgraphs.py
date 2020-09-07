"""
@Time   : 2020/6/22 5:40 \u4e0b\u5348
@Author : sunjiawei
@E-mail : j.w.sun1992@gmail.com
"""
from configparser import ConfigParser
from py2neo import Graph, Node, Relationship

cfg = ConfigParser()
with open('./config_files/application.cfg') as (f):
    cfg.read_file(f)
neo4j_url = cfg.get('neo4j', 'url')
auth = eval(cfg.get('neo4j', 'auth'))
with open('./config_files/neo4j-structure.cfg') as (f):
    cfg.read_file(f)
fused_entities = cfg.get('fuse', 'entities').split(',')
fused_rel = cfg.get('fuse', 'relationships').split(',')
fused_pros = cfg.get('fuse', 'properties').split('&')
fused_pros = [i.split(',') for i in fused_pros]
cms_entities = cfg.get('cms', 'entities').split(',')
if len(fused_entities) != len(cms_entities):
    fused_entities = cms_entities


def delete_old(label):
    """删除已有的融合结果。
    
    Args:
        label(str): 节点的标签
    
    Returns:
    
    """
    graph = Graph(neo4j_url, auth=auth)
    graph.run(f'match (n:`{label}`)-[r]-() delete r')
    graph.run(f'match (n:`{label}`) delete n')


def create_subgraph(label, sub_graph):
    """根据融合结果，创建新的图。
    
    Args:
        label(str): 新图的标签
        sub_graph(dict): 包含融合结果的字典
    
    Returns:
    
    """
    graph = Graph(neo4j_url, auth=auth)
    tx = graph.begin()
    root_node = generate_node([fused_entities[0], label], fused_pros[0], *sub_graph['val'])
    tx.create(root_node)

    def func(parent_node, graph_data, i):
        data = graph_data['children']
        for k in data:
            node = generate_node([fused_entities[i], label], fused_pros[i], *data[k]['val'])
            tx.create(node)
            rel = fused_rel[i - 1]
            tx.create(Relationship(parent_node, rel, node))
            if data[k]['children'] == {}:
                continue
            if i != len(fused_entities) - 1:
                j = i + 1
                graph_data = data[k]
                func(node, graph_data, j)

    func(root_node, sub_graph, 1)
    tx.commit()


def generate_node(label, pros, node_id1=None, node_id2=None, node_id3=None):
    """根据融合结果的id，来生成融合图。
    
    Args:
        label(list): 新节点的标签
        pros(list): 新节点需要从旧节点继承的属性
        node_id1(str): 旧节点id
        node_id2(str): 旧节点id
        node_id3(str): 旧节点id
    
    Returns:
        A `py2neo.Node` object
    """
    graph = Graph(neo4j_url, auth=auth)
    data = {'cmsId': node_id1 if node_id1 else '', 'pmsId': node_id2 if node_id2 else '',
            'gisId': node_id3 if node_id3 else ''}
    for p in pros:
        val = ''
        for id_ in [node_id1, node_id2, node_id3]:
            if id_ is not None:
                val = graph.run(f'match(n) where id(n)={id_} return n.{p} as p').data()[0]['p']
                if val:
                    break
                continue

        data[f'{p}'] = val

    return Node(*label, **data)


if __name__ == '__main__':
    delete_old('merge')
