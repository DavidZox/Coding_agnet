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
    ArcNode(int v, int w, ArcNode* n) : adjVex(v), weight(w), next(n) {}
};

template <typename VertexType>
struct _vNode {
    VertexType v;
    ArcNode* arcList;
    _vNode(VertexType val) : v(val), arcList(nullptr) {}
};

template <typename VertexType>
class AdjacencyListGraph {
private:
    bool _isDirected;
    int _vexNum;
    int _arcNum;
    _vNode<VertexType>** _vexList;

public:
    AdjacencyListGraph(int vexNum, int arcNum, bool isDirected)
        : _isDirected(isDirected), _vexNum(vexNum), _arcNum(arcNum) {
        _vexList = new _vNode<VertexType>*[_vexNum];
        for (int i = 0; i < _vexNum; ++i) {
            _vexList[i] = nullptr;
        }
    }

    ~AdjacencyListGraph() {
        for (int i = 0; i < _vexNum; ++i) {
            if (_vexList[i]) {
                ArcNode* curr = _vexList[i]->arcList;
                while (curr) {
                    ArcNode* temp = curr;
                    curr = curr->next;
                    delete temp;
                }
                delete _vexList[i];
            }
        }
        delete[] _vexList;
    }

    int locateVex(VertexType value) const {
        for (int i = 0; i < _vexNum; ++i) {
            if (_vexList[i] && _vexList[i]->v == value) {
                return i;
            }
        }
        return -1;
    }

    bool setVexes(const std::vector<VertexType>& vexes) {
        if (vexes.size() != static_cast<size_t>(_vexNum)) {
            throw std::out_of_range("Vertex count mismatch");
        }
        for (int i = 0; i < _vexNum; ++i) {
            if (_vexList[i]) delete _vexList[i];
            _vexList[i] = new _vNode<VertexType>(vexes[i]);
        }
        return true;
    }

    bool setArcs(const std::vector<std::tuple<VertexType, VertexType, int>>& arcs) {
        for (const auto& arc : arcs) {
            int u = locateVex(std::get<0>(arc));
            int v = locateVex(std::get<1>(arc));
            int w = std::get<2>(arc);

            if (u != -1 && v != -1) {
                _vexList[u]->arcList = new ArcNode(v, w, _vexList[u]->arcList);
                if (!_isDirected) {
                    _vexList[v]->arcList = new ArcNode(u, w, _vexList[v]->arcList);
                }
            }
        }
        return true;
    }

    std::vector<VertexType> dfs_noRes() {
        std::vector<VertexType> res;
        if (_vexNum == 0) return res;

        std::vector<bool> visited(_vexNum, false);
        Stack<int> s;

        // Start from the first vertex (index 0)
        s.push(0);

        while (!s.empty()) {
            int currIdx = s.top();
            s.pop();

            if (!visited[currIdx]) {
                visited[currIdx] = true;
                res.push_back(_vexList[currIdx]->v);

                // To simulate standard DFS order (visiting neighbors in order), 
                // we need to push them onto the stack in reverse order.
                // However, the adjacency list is a linked list (head is newest).
                // We collect neighbors and push them to stack.
                std::vector<std::pair<int, int>> neighbors;
                ArcNode* currArc = _vexList[currIdx]->arcList;
                while (currArc) {
                    if (!visited[currArc->adjVex]) {
                        neighbors.push_back({currArc->adjVex, currArc->weight});
                    }
                    currArc = currArc->next;
                }
                // Push in reverse to process the "first" neighbor first
                for (int i = neighbors.size() - 1; i >= 0; --i) {
                    s.push(neighbors[i].first);
                }
            }
        }
        return res;
    }

    std::vector<VertexType> bfs() {
        return bfs(_vexList[0]->v);
    }

    std::vector<VertexType> bfs(VertexType startVal) {
        std::vector<VertexType> res;
        int startIdx = locateVex(startVal);
        if (startIdx == -1) return res;

        std::vector<bool> visited(_vexNum, false);
        Queue<int> q;

        visited[startIdx] = true;
        q.push(startIdx);

        while (!q.empty()) {
            int currIdx = q.pop();
            res.push_back(_vexList[currIdx]->v);

            ArcNode* currArc = _vexList[currIdx]->arcList;
            while (currArc) {
                if (!visited[currArc->adjVex]) {
                    visited[currArc->adjVex] = true;
                    q.push(currArc->adjVex);
                }
                currArc = currArc->next;
            }
        }
        return res;
    }

    friend std::ostream& operator<<(std::ostream& os, const AdjacencyListGraph& graph) {
        os << "Adjacency Table：\n";
        for (int i = 0; i < graph._vexNum; ++i) {
            os << graph._vexList[i]->v;
            ArcNode* curr = graph._vexList[i]->arcList;
            while (curr) {
                os << "\t" << curr->adjVex << " -> " << graph._vexList[curr->adjVex]->v << " " << curr->weight;
                curr = curr->next;
            }
            os << " -> ^\n";
        }
        return os;
    }
};

#endif
