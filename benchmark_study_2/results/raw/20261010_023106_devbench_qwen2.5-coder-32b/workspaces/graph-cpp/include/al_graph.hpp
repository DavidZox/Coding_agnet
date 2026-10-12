#ifndef AL_GRAPH_HPP
#define AL_GRAPH_HPP

#include <iostream>
#include <vector>
#include <tuple>
#include <string>
#include <algorithm>
#include "queue.hpp"
#include "stack.hpp"

template <typename VertexType>
class AdjacencyListGraph {
private:
    bool _isDirected;
    int _vexNum;
    int _arcNum;
    struct ArcNode {
        int adjVex;
        int weight;
        ArcNode* next;
        ArcNode(int v, int w) : adjVex(v), weight(w), next(nullptr) {}
    };
    struct _vNode {
        VertexType v;
        ArcNode* next;
        _vNode() : next(nullptr) {}
    };
    std::vector<_vNode> _vexList;

public:
    AdjacencyListGraph(int vexNum, int arcNum, bool isDirected)
        : _isDirected(isDirected), _vexNum(vexNum), _arcNum(arcNum) {
        _vexList.resize(static_cast<size_t>(vexNum));
    }

    ~AdjacencyListGraph() {
        for (auto& vNode : _vexList) {
            ArcNode* node = vNode.next;
            while (node) {
                ArcNode* temp = node;
                node = node->next;
                delete temp;
            }
        }
    }

    bool setVexes(const std::vector<VertexType>& vexes) {
        if (vexes.size() != static_cast<size_t>(_vexNum)) return false;
        for (int i = 0; i < _vexNum; ++i) {
            _vexList[static_cast<size_t>(i)].v = vexes[static_cast<size_t>(i)];
        }
        return true;
    }

    bool setArcs(const std::vector<std::tuple<int, int, int>>& arcs) {
        if (arcs.size() != static_cast<size_t>(_arcNum)) return false;
        for (const auto& arc : arcs) {
            int start = std::get<0>(arc);
            int end = std::get<1>(arc);
            int weight = std::get<2>(arc);
            ArcNode* newNode = new ArcNode(end, weight);
            newNode->next = _vexList[static_cast<size_t>(start)].next;
            _vexList[static_cast<size_t>(start)].next = newNode;
            if (!_isDirected) {
                ArcNode* reverseNode = new ArcNode(start, weight);
                reverseNode->next = _vexList[static_cast<size_t>(end)].next;
                _vexList[static_cast<size_t>(end)].next = reverseNode;
            }
        }
        return true;
    }

    int locateVex(VertexType value) {
        for (int i = 0; i < _vexNum; ++i) {
            if (_vexList[static_cast<size_t>(i)].v == value) return i;
        }
        return -1;
    }

    std::vector<VertexType> dfs_noRes() {
        std::vector<VertexType> result;
        std::vector<bool> visited(static_cast<size_t>(_vexNum), false);
        Stack<int> stack;
        stack.push(0);
        while (!stack.empty()) {
            int current = stack.top();
            stack.pop();
            if (!visited[static_cast<size_t>(current)]) {
                visited[static_cast<size_t>(current)] = true;
                result.push_back(_vexList[static_cast<size_t>(current)].v);
                ArcNode* node = _vexList[static_cast<size_t>(current)].next;
                while (node) {
                    if (!visited[static_cast<size_t>(node->adjVex)]) {
                        stack.push(node->adjVex);
                    }
                    node = node->next;
                }
            }
        }
        return result;
    }

    std::vector<VertexType> bfs() {
        std::vector<VertexType> result;
        std::vector<bool> visited(static_cast<size_t>(_vexNum), false);
        Queue<int> queue;
        queue.push(0);
        visited[0] = true;
        while (!queue.empty()) {
            int current = queue.front();
            queue.pop();
            result.push_back(_vexList[static_cast<size_t>(current)].v);
            ArcNode* node = _vexList[static_cast<size_t>(current)].next;
            while (node) {
                if (!visited[static_cast<size_t>(node->adjVex)]) {
                    queue.push(node->adjVex);
                    visited[static_cast<size_t>(node->adjVex)] = true;
                }
                node = node->next;
            }
        }
        return result;
    }

    friend std::ostream& operator<<(std::ostream& os, const AdjacencyListGraph& graph) {
        os << "Adjacency Table：" << std::endl;
        for (int i = 0; i < graph._vexNum; ++i) {
            os << i << "\t" << graph._vexList[static_cast<size_t>(i)].v << "\t->\t";
            ArcNode* node = graph._vexList[static_cast<size_t>(i)].next;
            while (node) {
                os << node->adjVex << "\t" << node->weight << "\t->\t";
                node = node->next;
            }
            os << "^" << std::endl;
        }
        return os;
    }
};

#endif // AL_GRAPH_HPP
