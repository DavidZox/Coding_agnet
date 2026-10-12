#ifndef AL_GRAPH_HPP
#define AL_GRAPH_HPP

#include <vector>
#include <tuple>
#include <iostream>
#include "queue.hpp"
#include "stack.hpp"

template <typename VertexType>
class AdjacencyListGraph {
private:
    struct ArcNode {
        int adjVex;
        int weight;
        ArcNode* next;
        ArcNode(int v, int w, ArcNode* n) : adjVex(v), weight(w), next(n) {}
    };

    struct _vNode{
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

    int locateVex(VertexType value) {
        for (int i = 0; i < _vexNum; ++i) {
            if (_vexList[i] && _vexList[i]->v == value) return i;
        }
        return -1;
    }

    bool setVexes(std::vector<VertexType> vexes) {
        if (vexes.size() != static_cast<size_t>(_vexNum)) return false;
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
            _vexList[i] = new _vNode(vexes[i], nullptr);
        }
        return true;
    }

    bool setArcs(std::vector<std::tuple<VertexType, VertexType, int>> arcs) {
        for (auto& arc : arcs) {
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

        Stack<int> s;
        std::vector<bool> visited(_vexNum, false);

        for (int i = 0; i < _vexNum; ++i) {
            if (!visited[i]) {
                s.push(i);
                while (!s.empty()) {
                    int curr = s.top();
                    s.pop();

                    if (!visited[curr]) {
                        visited[curr] = true;
                        res.push_back(_vexList[curr]->v);

                        std::vector<ArcNode*> neighbors;
                        ArcNode* temp = _vexList[curr]->nextArc;
                        while(temp) {
                            neighbors.push_back(temp);
                            temp = temp->next;
                        }
                        for (int j = neighbors.size() - 1; j >= 0; --j) {
                            if (!visited[neighbors[j]->adjVex]) {
                                s.push(neighbors[j]->adjVex);
                            }
                        }
                    }
                }
            }
        }
        return res;
    }

    std::vector<VertexType> bfs() {
        if (_vexNum == 0) return {};
        return bfs(_vexList[0]->v);
    }

    std::vector<VertexType> bfs(VertexType startVex) {
        std::vector<VertexType> res;
        int startIdx = locateVex(startVex);
        if (startIdx == -1) return res;

        Queue<int> q;
        std::vector<bool> visited(_vexNum, false);

        visited[startIdx] = true;
        q.push(startIdx);

        while (!q.empty()) {
            int curr = q.front();
            q.pop();
            res.push_back(_vexList[curr]->v);

            ArcNode* temp = _vexList[curr]->nextArc;
            while (temp) {
                if (!visited[temp->adjVex]) {
                    visited[temp->adjVex] = true;
                    q.push(temp->adjVex);
                }
                temp = temp->next;
            }
        }
        return res;
    }

    friend std::ostream& operator<<(std::ostream& os, const AdjacencyListGraph& graph) {
        for (int i = 0; i < graph._vexNum; ++i) {
            if (graph._vexList[i]) {
                os << graph._vexList[i]->v << "\t";
                ArcNode* curr = graph._vexList[i]->nextArc;
                if (curr == nullptr) {
                    os << "->\t^\n";
                } else {
                    os << curr->adjVex << "\t->\t";
                    ArcNode* iter = curr;
                    while (iter) {
                        os << iter->adjVex << "\t" << iter->weight << "\t->\t";
                        iter = iter->next;
                    }
                    os << "^\n";
                }
            }
        }
        return os;
    }
};
#endif
