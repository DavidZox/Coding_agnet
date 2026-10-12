#ifndef AL_GRAPH_HPP
#define AL_GRAPH_HPP

#include <iostream>
#include <vector>
#include <tuple>
#include <queue.hpp>
#include <stack.hpp>

template <typename VertexType>
class AdjacencyListGraph {
private:
    struct ArcNode {
        int adjVex;
        int weight;
        ArcNode* next;

        ArcNode(int adjVex, int weight) : adjVex(adjVex), weight(weight), next(nullptr) {}
    };

    struct _vNode {
        VertexType v;
        ArcNode* next;

        _vNode(VertexType v) : v(v), next(nullptr) {}
    };

    bool _isDirected;
    int _vexNum;
    int _arcNum;
    std::vector<_vNode> _vexList;

    int locateVex(VertexType value) const {
        for (int i = 0; i < _vexNum; ++i) {
            if (_vexList[i].v == value) {
                return i;
            }
        }
        return -1;
    }

public:
    AdjacencyListGraph(int vexNum, int arcNum, bool isDirected)
        : _isDirected(isDirected), _vexNum(vexNum), _arcNum(arcNum), _vexList(vexNum) {}

    bool setVexer(const std::vector<VertexType>& vexes) {
        if (vexes.size() != _vexNum) {
            return false;
        }
        for (int i = 0; i < _vexNum; ++i) {
            _vexList[i].v = vexes[i];
        }
        return true;
    }

    bool setArcs(const std::vector<std::tuple<VertexType, VertexType, int>>& arcs) {
        if (arcs.size() != _arcNum) {
            return false;
        }
        for (const auto& arc : arcs) {
            int start = locateVex(std::get<0>(arc));
            int end = locateVex(std::get<1>(arc));
            int weight = std::get<2>(arc);
            if (start == -1 || end == -1) {
                return false;
            }
            ArcNode* newNode = new ArcNode(end, weight);
            newNode->next = _vexList[start].next;
            _vexList[start].next = newNode;
            if (!_isDirected) {
                ArcNode* reverseNode = new ArcNode(start, weight);
                reverseNode->next = _vexList[end].next;
                _vexList[end].next = reverseNode;
            }
        }
        return true;
    }

    std::vector<VertexType> dfs_noRes() {
        std::vector<VertexType> result;
        std::vector<bool> visited(_vexNum, false);
        Stack<int> stack;
        stack.push(0);
        while (!stack.empty()) {
            int current = stack.top();
            stack.pop();
            if (!visited[current]) {
                visited[current] = true;
                result.push_back(_vexList[current].v);
                ArcNode* node = _vexList[current].next;
                while (node != nullptr) {
                    if (!visited[node->adjVex]) {
                        stack.push(node->adjVex);
                    }
                    node = node->next;
                }
            }
        }
        return result;
    }

    std::vector<VertexType> bfs() {
        return bfs(_vexList[0].v);
    }

    std::vector<VertexType> bfs(VertexType start) {
        std::vector<VertexType> result;
        std::vector<bool> visited(_vexNum, false);
        Queue<int> queue;
        int startIndex = locateVex(start);
        if (startIndex == -1) {
            return result;
        }
        queue.push(startIndex);
        visited[startIndex] = true;
        while (!queue.empty()) {
            int current = queue.front();
            queue.pop();
            result.push_back(_vexList[current].v);
            ArcNode* node = _vexList[current].next;
            while (node != nullptr) {
                if (!visited[node->adjVex]) {
                    queue.push(node->adjVex);
                    visited[node->adjVex] = true;
                }
                node = node->next;
            }
        }
        return result;
    }

    friend std::ostream& operator<<(std::ostream& os, const AdjacencyListGraph& graph) {
        os << "Adjacency List:\n";
        for (int i = 0; i < graph._vexNum; ++i) {
            os << graph._vexList[i].v << "\t";
            ArcNode* node = graph._vexList[i].next;
            while (node != nullptr) {
                os << node->adjVex << " " << node->weight << " -> ";
                node = node->next;
            }
            os << "^" << "\n";
        }
        return os;
    }
};

#endif // AL_GRAPH_HPP
