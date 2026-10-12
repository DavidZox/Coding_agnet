#ifndef AL_GRAPH_HPP
#define AL_GRAPH_HPP

#include <vector>
#include <tuple>
#include <iostream>
#include "queue.hpp"
#include "stack.hpp"

namespace graph {

template <typename VertexType>
class AdjacencyListGraph {
private:
    struct ArcNode {
        int adjVex;
        int weight;
        ArcNode* next;
        ArcNode(int v, int w, ArcNode* n = nullptr) : adjVex(v), weight(w), next(n) {}
    };

    struct _vNode {
        VertexType v;
        ArcNode* next;
        _vNode(VertexType val) : v(val), next(nullptr) {}
    };

    bool _isDirected;
    int _vexNum;
    int _arcNum;
    std::vector<_vNode> _vertices;

public:
    AdjacencyListGraph(int vexNum, int arcNum, bool isDirected)
        : _isDirected(isDirected), _vexNum(vexNum), _arcNum(arcNum) {
        _vertices.resize(vexNum);
    }

    bool setVexes(const std::vector<VertexType>& vexes) {
        if (vexes.size() != _vexNum) return false;
        for (int i = 0; i < _vexNum; ++i) {
            _vertices[i].v = vexes[i];
        }
        return true;
    }

    bool setArcs(const std::vector<std::tuple<int, int, int>>& arcs) {
        if (arcs.size() != _arcNum) return false;
        for (const auto& arc : arcs) {
            int start = std::get<0>(arc);
            int end = std::get<1>(arc);
            int weight = std::get<2>(arc);
            if (start == -1 || end == -1) return false;
            _vertices[start].next = new ArcNode(end, weight, _vertices[start].next);
            if (!_isDirected) {
                _vertices[end].next = new ArcNode(start, weight, _vertices[end].next);
            }
        }
        return true;
    }

    int locateVex(VertexType value) {
        for (int i = 0; i < _vexNum; ++i) {
            if (_vertices[i].v == value) return i;
        }
        return -1;
    }

    std::vector<VertexType> dfs_noRes() {
        std::vector<VertexType> result;
        std::vector<bool> visited(_vexNum, false);
        custom::Stack<int> stack;
        stack.push(0);
        while (!stack.empty()) {
            int current = stack.top();
            stack.pop();
            if (!visited[current]) {
                visited[current] = true;
                result.push_back(_vertices[current].v);
                ArcNode* node = _vertices[current].next;
                while (node) {
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
        return bfs(_vertices[0].v);
    }

    std::vector<VertexType> bfs(VertexType start) {
        std::vector<VertexType> result;
        std::vector<bool> visited(_vexNum, false);
        custom::Queue<int> queue;
        int startIndex = locateVex(start);
        if (startIndex == -1) return result;
        queue.push(startIndex);
        visited[startIndex] = true;
        while (!queue.empty()) {
            int current = queue.front();
            queue.pop();
            result.push_back(_vertices[current].v);
            ArcNode* node = _vertices[current].next;
            while (node) {
                if (!visited[node->adjVex]) {
                    visited[node->adjVex] = true;
                    queue.push(node->adjVex);
                }
                node = node->next;
            }
        }
        return result;
    }

    friend std::ostream& operator<<(std::ostream& os, const AdjacencyListGraph& graph) {
        os << "Adjacency List:\n";
        for (int i = 0; i < graph._vexNum; ++i) {
            os << graph._vertices[i].v << "\t";
            ArcNode* node = graph._vertices[i].next;
            while (node) {
                os << "->\t" << graph._vertices[node->adjVex].v << "\t" << node->weight << "\t";
                node = node->next;
            }
            os << "->\t^\n";
        }
        return os;
    }
};

} // namespace graph

#endif // AL_GRAPH_HPP
