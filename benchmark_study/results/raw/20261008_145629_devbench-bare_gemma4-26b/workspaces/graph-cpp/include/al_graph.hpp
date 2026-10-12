#ifndef AL_GRAPH_HPP
#define AL_GRAPH_HPP

#include <vector>
#include <tuple>
#include <iostream>
#include <algorithm>
#include "queue.hpp"
#include "stack.hpp"

template <typename VertexType>
struct ArcNode {
    int adjVex;
    int weight;
    ArcNode* next;
    ArcNode(int adj, int w, ArcNode* n = nullptr) : adjVex(adj), weight(w), next(n) {}
};

template <typename VertexType>
struct _vNode {
    VertexType v;
    ArcNode* head;
    _vNode(VertexType val) : v(val), head(nullptr) {}
};

template <typename VertexType>
class AdjacencyListGraph {
private:
    bool _isDirected;
    int _vexNum;
    int _arcNum;
    std::vector<_vNode<VertexType>> _vexList;

public:
    AdjacencyListGraph(int vexNum, int arcNum, bool isDirected)
        : _isDirected(isDirected), _vexNum(vexNum), _arcNum(arcNum) {
        _vexList.reserve(vexNum);
    }

    bool setVexer(const std::vector<VertexType>& vexes) {
        if (vexes.size() != static_cast<size_t>(_vexNum)) return false;
        _vexList.clear();
        for (const auto& v : vexes) {
            _vexList.emplace_back(v);
        }
        return true;
    }

    bool setArcs(const std::vector<std::tuple<VertexType, VertexType, int>>& arcs) {
        // Reset existing arcs
        for (auto& node : _vexList) {
            ArcNode* curr = node.head;
            while (curr) {
                ArcNode* next = curr->next;
                delete curr;
                curr = next;
            }
            node.head = nullptr;
        }

        int count = 0;
        for (const auto& arc : arcs) {
            int u = locateVex(std::get<0>(arc));
            int v = locateVex(std::get<1>(arc));
            if (u == -1 || v == -1) return false;

            int weight = std::get<2>(arc);
            _vexList[u].head = new ArcNode(v, weight, _vexList[u].head);
            count++;
            if (!_isDirected) {
                _vexList[v].head = new ArcNode(u, weight, _vexList[v].head);
                count++;
            }
        }
        _arcNum = count;
        return true;
    }

    int locateVex(VertexType value) const {
        for (int i = 0; i < _vexNum; ++i) {
            if (_vexList[i].v == value) return i;
        }
        return -1;
    }

    std::vector<VertexType> dfs_noRes() {
        std::vector<VertexType> res;
        if (_vexNum == 0) return res;

        std::vector<bool> visited(_vexNum, false);
        Stack<int> s;

        // Starting from the first vertex as per typical traversal requirements
        s.push(0);

        while (!s.empty()) {
            int u = s.top();
            s.pop();

            if (!visited[u]) {
                visited[u] = true;
                res.push_back(_vexList[u].v);
            }

            // To simulate standard DFS order (visiting neighbors in order), 
            // we push them to stack in reverse order.
            // However, for non-recursive DFS, we need to handle the "stack" of nodes to visit.
            // A common way is to push unvisited neighbors.
            
            // Note: Standard non-recursive DFS using a stack often visits nodes 
            // in a different order than recursive DFS unless handled carefully.
            // We will collect neighbors and push them.
            std::vector<std::pair<int, int>> neighbors;
            ArcNode* curr = _vexList[u].head;
            while (curr) {
                if (!visited[curr->adjVex]) {
                    neighbors.push_back({curr->adjVex, curr->weight});
                }
                curr = curr->next;
            }
            // Push in reverse to process in original order
            for (int i = neighbors.size() - 1; i >= 0; --i) {
                if (!visited[neighbors[i].first]) {
                    s.push(neighbors[i].first);
                }
            }
        }
        return res;
    }

    std::vector<VertexType> bfs() {
        return bfs(_vexList[0].v);
    }

    std::vector<VertexType> bfs(VertexType startVex) {
        std::vector<VertexType> res;
        int startIdx = locateVex(startVex);
        if (startIdx == -1) return res;

        std::vector<bool> visited(_vexNum, false);
        Queue<int> q;

        visited[startIdx] = true;
        q.push(startIdx);

        while (!q.empty()) {
            int u = q.pop();
            res.push_back(_vexList[u].v);

            ArcNode* curr = _vexList[u].head;
            while (curr) {
                if (!visited[curr->adjVex]) {
                    visited[curr->adjVex] = true;
                    q.push(curr->adjVex);
                }
                curr = curr->next;
            }
        }
        return res;
    }

    friend std::ostream& operator<<(std::ostream& os, const AdjacencyListGraph<VertexType>& graph) {
        for (int i = 0; i < graph._vexNum; ++i) {
            os << graph._vexList[i].v << "\t";
            ArcNode* curr = graph._vexList[i].head;
            while (curr) {
                os << curr->adjVex << "\t->\t" << curr->adjVex << "\t" << curr->weight << "\t->\t";
                curr = curr->next;
            }
            os << "^\t";
            if (i < graph._vexNum - 1) os << "\n";
        }
        return os;
    }
};

#endif
