#ifndef AL_GRAPH_HPP
#define AL_GRAPH_HPP

#include <vector>
#include <tuple>
#include <iostream>
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

    int locateVex(VertexType value) {
        for (int i = 0; i < _vexNum; ++i) {
            if (_vexList[i] && _vexList[i]->v == value) return i;
        }
        return -1;
    }

    bool setVexer(std::vector<VertexType> vexes) {
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

        std::vector<bool> visited(_vexNum, false);
        Stack<int> s;

        // Starting from the first vertex as per standard traversal logic
        s.push(0);

        while (!s.empty()) {
            int u = s.top();
            s.pop();

            if (!visited[u]) {
                visited[u] = true;
                res.push_back(_vexList[u]->v);

                // To simulate DFS order (visiting neighbors in order), 
                // we push them to stack in reverse order.
                std::vector<int> neighbors;
                ArcNode* curr = _vexList[u]->nextArc;
                while (curr) {
                    if (!visited[curr->adjVex]) {
                        neighbors.push_back(curr->adjVex);
                    }
                    curr = curr->next;
                }
                // Push in reverse order so the first neighbor in the list is popped first
                for (int i = static_cast<int>(neighbors.size()) - 1; i >= 0; --i) {
                    s.push(neighbors[i]);
                }
            }
        }
        return res;
    }

    std::vector<VertexType> bfs(VertexType startNode) {
        std::vector<VertexType> res;
        int startIdx = locateVex(startNode);
        if (startIdx == -1) return res;

        std::vector<bool> visited(_vexNum, false);
        Queue<int> q;

        visited[startIdx] = true;
        q.push(startIdx);

        while (!q.empty()) {
            int u = q.front();
            q.pop();
            res.push_back(_vexList[u]->v);

            ArcNode* curr = _vexList[u]->nextArc;
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

    std::vector<VertexType> bfs() {
        if (_vexNum == 0) return {};
        return bfs(_vexList[0]->v);
    }

    friend std::ostream& operator<<(std::ostream& os, const AdjacencyListGraph& graph) {
        for (int i = 0; i < graph._vexNum; ++i) {
            os << i << "\t";
            ArcNode* curr = graph._vexList[i]->nextArc;
            while (curr) {
                os << curr->adjVex << "\t" << "->\t" << curr->adjVex << "\t" << curr->weight << "\t->\t";
                curr = curr->next;
            }
            os << "^\t";
            if (i < graph._vexNum - 1) os << "\n";
        }
        return os;
    }
};

#endif
