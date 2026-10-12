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
        ArcNode(int adj, int w, ArcNode* n) : adjVex(adj), weight(w), next(n) {}
    };

    struct _vNode {
        VertexType v;
        ArcNode* arcHead;
        _vNode* next;
        _vNode(VertexType val) : v(val), arcHead(nullptr), next(nullptr) {}
    };

    bool _isDirected;
    int _vexNum;
    int _arcNum;
    _vNode* _vHead;
    std::vector<VertexType> _vexList;

    void clear() {
        _vNode* currV = _vHead;
        while (currV) {
            _vNode* nextV = currV->next;
            ArcNode* currA = currV->arcHead;
            while (currA) {
                ArcNode* nextA = currA->next;
                delete currA;
                currA = nextA;
            }
            delete currV;
            currV = nextV;
        }
        _vHead = nullptr;
    }

public:
    AdjacencyListGraph(int vexNum, int arcNum, bool isDirected)
        : _isDirected(isDirected), _vexNum(vexNum), _arcNum(arcNum), _vHead(nullptr) {}

    ~AdjacencyListGraph() {
        clear();
    }

    int locateVex(VertexType value) const {
        for (int i = 0; i < _vexNum; ++i) {
            if (_vexList[i] == value) return i;
        }
        return -1;
    }

    bool setVexer(std::vector<VertexType> vexes) {
        if (vexes.size() != static_cast<size_t>(_vexNum)) return false;
        clear();
        _vexList = vexes;
        _vHead = nullptr;
        _vNode** last = &_vHead;
        for (const auto& v : _vexList) {
            *last = new _vNode(v);
            last = &((*last)->next);
        }
        return true;
    }

    bool setArcs(std::vector<std::tuple<VertexType, VertexType, int>> arcs) {
        if (arcs.size() != static_cast<size_t>(_arcNum)) return false;
        // Clear existing arcs but keep vertices
        _vNode* currV = _vHead;
        while (currV) {
            ArcNode* currA = currV->arcHead;
            while (currA) {
                ArcNode* nextA = currA->next;
                delete currA;
                currA = nextA;
            }
            currV->arcHead = nullptr;
            currV = currV->next;
        }

        for (const auto& arc : arcs) {
            int u = locateVex(std::get<0>(arc));
            int v = locateVex(std::get<1>(arc));
            int w = std::get<2>(arc);
            if (u == -1 || v == -1) return false;

            // Add u -> v
            _vNode* uNode = _vHead;
            for (int i = 0; i < u; ++i) uNode = uNode->next;
            uNode->arcHead = new ArcNode(v, w, uNode->arcHead);

            if (!_isDirected) {
                // Add v -> u
                _vNode* vNode = _vHead;
                for (int i = 0; i < v; ++i) vNode = vNode->next;
                vNode->arcHead = new ArcNode(u, w, vNode->arcHead);
            }
        }
        return true;
    }

    std::vector<VertexType> dfs_noRes() {
        std::vector<VertexType> res;
        if (_vexNum == 0) return res;

        std::vector<bool> visited(_vexNum, false);
        Stack<int> s;

        s.push(0); // Start from first vertex index

        while (!s.empty()) {
            int u = s.top();
            s.pop();
            if (!visited[u]) {
                visited[u] = true;
                res.push_back(_vexList[u]);

                // To simulate standard DFS order (visiting neighbors in order), 
                // we should push neighbors to stack in reverse order.
                // However, the requirement is non-recursive DFS.
                // A common way is to push all unvisited neighbors.
                _vNode* currV = _vHead;
                for (int i = 0; i < u; ++i) currV = currV->next;

                // Collect neighbors to push in reverse to maintain order if needed
                std::vector<int> neighbors;
                ArcNode* currA = currV->arcHead;
                while (currA) {
                    if (!visited[currA->adjVex]) {
                        neighbors.push_back(currA->adjVex);
                    }
                    currA = currA->next;
                }
                for (int i = neighbors.size() - 1; i >= 0; --i) {
                    s.push(neighbors[i]);
                }
            }
        }
        return res;
    }

    std::vector<VertexType> bfs() {
        return bfs(_vexList[0]);
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
            int u = q.pop();
            res.push_back(_vexList[u]);

            _vNode* currV = _vHead;
            for (int i = 0; i < u; ++i) currV = currV->next;

            ArcNode* currA = currV->arcHead;
            while (currA) {
                if (!visited[currA->adjVex]) {
                    visited[currA->adjVex] = true;
                    q.push(currA->adjVex);
                }
                currA = currA->next;
            }
        }
        return res;
    }

    friend std::ostream& operator<<(std::ostream& os, const AdjacencyListGraph& alg) {
        _vNode* currV = alg._vHead;
        for (int i = 0; i < alg._vexNum; ++i) {
            os << alg._vexList[i] << "\t";
            ArcNode* currA = currV->arcHead;
            while (currA) {
                os << alg._vexList[currA->adjVex] << "\t" << "->\t" 
                   << alg._vexList[currA->adjVex] << "\t" << currA->weight << "\t" << "->\t";
                currA = currA->next;
            }
            os << "^" << std::endl;
            currV = currV->next;
        }
        return os;
    }
};

#endif
