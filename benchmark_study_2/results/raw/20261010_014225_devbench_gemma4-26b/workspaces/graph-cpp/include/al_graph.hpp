#ifndef AL_GRAPH_HPP
#define AL_GRAPH_HPP

#include <vector>
#include <iostream>
#include <tuple>
#include <algorithm>
#include "stack.hpp"
#include "queue.hpp"

template <typename VertexType>
class AdjacencyListGraph {
private:
    struct ArcNode {
        int adjVex;
        int weight;
        ArcNode* next;
        ArcNode(int v, int w, ArcNode* n) : adjVex(v), weight(w), next(n) {}
    };

    struct _vNode {
        VertexType v;
        ArcNode* nextArc;
        _vNode(VertexType val, ArcNode* n) : v(val), nextArc(n) {}
    };

    bool _isDirected;
    int _vexNum;
    int _arcNum;
    _vNode** _vexList;

public:
    AdjacencyListGraph(int vexNum, int arcNum, bool isDirected)
        : _isDirected(isDirected), _vexNum(vexNum), _arcNum(arcNum) {
        _vexList = new _vNode*[vexNum];
        for (int i = 0; i < vexNum; ++i) {
            _vexList[i] = nullptr;
        }
    }

    ~AdjacencyListGraph() {
        for (int i = 0; i < _vexNum; ++i) {
            if (_vexList[i]) {
                ArcNode* currArc = _vexList[i]->nextArc;
                while (currArc) {
                    ArcNode* temp = currArc;
                    currArc = currArc->next;
                    delete temp;
                }
                delete _vexList[i];
            }
        }
        delete[] _vexList;
    }

    int locateVex(VertexType value) const {
        for (int i = 0; i < _vexNum; ++i) {
            if (_vexList[i] && _vexList[i]->v == value) return i;
        }
        return -1;
    }

    bool setVexes(const std::vector<VertexType>& vexes) {
        if (vexes.size() != static_cast<size_t>(_vexNum)) return false;
        for (int i = 0; i < _vexNum; ++i) {
            if (_vexList[i]) delete _vexList[i];
            _vexList[i] = new _vNode(vexes[i], nullptr);
        }
        return true;
    }

    bool setArcs(const std::vector<std::tuple<VertexType, VertexType, int>>& arcs) {
        for (const auto& arc : arcs) {
            int u = locateVex(std::get<0>(arc));
            int v = locateVex(std::get<1>(arc));
            int w = std::get<2>(arc);
            if (u == -1 || v == -1) return false;

            _vexList[u]->nextArc = new ArcNode(v, w, _vexList[u]->nextArc);
            if (!_isDirected) {
                _vexList[v]->nextArc = new ArcNode(u, w, _vexList[v]->nextArc);
            }
        }
        return true;
    }

    std::vector<VertexType> dfs_noRes() {
        std::vector<VertexType> res;
        if (_vexNum == 0) return res;

        std::vector<bool> visited(_vexNum, false);
        Stack<int> s;

        // Find the first valid vertex index to start DFS
        int startIdx = -1;
        for(int i = 0; i < _vexNum; ++i) {
            if (_vexList[i] && _vexList[i]->v != 0) {
                startIdx = i;
                break;
            }
        }
        
        if (startIdx == -1) return res;
        s.push(startIdx);

        while (!s.empty()) {
            int curr = s.top();
            s.pop();

            if (!visited[curr]) {
                visited[curr] = true;
                res.push_back(_vexList[curr]->v);

                // Collect all neighbors to sort them
                std::vector<int> neighborIndices;
                ArcNode* temp = _vexList[curr]->nextArc;
                while (temp) {
                    neighborIndices.push_back(temp->adjVex);
                    temp = temp->next;
                }

                // To ensure we visit neighbors in increasing order of their index,
                // we must push them onto the stack in DECREASING order.
                std::sort(neighborIndices.begin(), neighborIndices.end(), std::greater<int>());

                for (int neighborIdx : neighborIndices) {
                    if (!visited[neighborIdx]) {
                        s.push(neighborIdx);
                    }
                }
            }
        }
        return res;
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
            int curr = q.pop();
            res.push_back(_vexList[curr]->v);

            // Collect neighbors to sort them for consistent BFS order
            std::vector<int> neighborIndices;
            ArcNode* temp = _vexList[curr]->nextArc;
            while (temp) {
                neighborIndices.push_back(temp->adjVex);
                temp = temp->next;
            }
            std::sort(neighborIndices.begin(), neighborIndices.end());

            for (int neighborIdx : neighborIndices) {
                if (!visited[neighborIdx]) {
                    visited[neighborIdx] = true;
                    q.push(neighborIdx);
                }
            }
        }
        return res;
    }

    std::vector<VertexType> bfs() {
        if (_vexNum == 0) return {};
        // Find the first valid vertex index to start BFS
        int startIdx = -1;
        for(int i = 0; i < _vexNum; ++i) {
            if (_vexList[i] && _vexList[i]->v != 0) {
                startIdx = i;
                break;
            }
        }
        if (startIdx == -1) return {};
        return bfs(_vexList[startIdx]->v);
    }

    friend std::ostream& operator<<(std::ostream& os, const AdjacencyListGraph& graph) {
        for (int i = 0; i < graph._vexNum; ++i) {
            os << i << " ";
            
            std::vector<std::pair<int, int>> neighbors;
            ArcNode* curr = graph._vexList[i]->nextArc;
            while (curr) {
                neighbors.push_back({curr->adjVex, curr->weight});
                curr = curr->next;
            }
            std::sort(neighbors.begin(), neighbors.end());

            for (const auto& p : neighbors) {
                os << p.first << " " << p.second << " -> ";
            }
            os << "^" << (i == graph._vexNum - 1 ? "" : " ") << std::endl;
        }
        return os;
    }
};

#endif
