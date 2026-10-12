#ifndef AL_GRAPH_HPP
#define AL_GRAPH_HPP

#include <vector>
#include <iostream>
#include <tuple>
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
            ArcNode* currArc = _vexList[i]->nextArc;
            while (currArc) {
                ArcNode* temp = currArc;
                currArc = currArc->next;
                delete temp;
            }
            delete _vexList[i];
        }
        delete[] _vexList;
    }

    int locateVex(VertexType value) const {
        for (int i = 0; i < _vexNum; ++i) {
            if (_vexList[i]->v == value) return i;
        }
        return -1;
    }

    bool setVexer(const std::vector<VertexType>& vexes) {
        if (vexes.size() != static_cast<size_t>(_vexNum)) return false;
        for (int i = 0; i < _vexNum; ++i) {
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

        // Start from the first vertex (index 0) as per typical traversal start
        s.push(0);

        while (!s.empty()) {
            int curr = s.top();
            s.pop();

            if (!visited[curr]) {
                visited[curr] = true;
                res.push_back(_vexList[curr]->v);
            }

            // To match standard DFS order (visiting neighbors in order), 
            // we push them to stack in reverse order.
            // However, the requirement is non-recursive DFS.
            // A common non-recursive DFS uses a stack of (vertex, neighbor_pointer).
            // But for simplicity and following the UML/PRD, we use a standard stack approach.
            // To ensure we visit neighbors, we need to handle the "backtracking" logic.
            // Let's use a more robust non-recursive DFS:
        }
        // Re-implementing non-recursive DFS to correctly handle the "visit" vs "explore"
        res.clear();
        std::fill(visited.begin(), visited.end(), false);
        Stack<int> stack;
        
        // We'll use a helper to simulate the recursion stack
        // Since we can't use recursion, we store the current vertex and its next neighbor to visit
        struct State {
            int vIdx;
            ArcNode* nextArc;
        };
        // Since we can't define a new struct easily inside the method for a template, 
        // let's use a simpler approach: push all unvisited neighbors to stack.
        // Note: Standard non-recursive DFS with a single stack of vertices:
        
        stack.push(0);
        while(!stack.empty()){
            int u = stack.top();
            stack.pop();
            
            if(!visited[u]){
                visited[u] = true;
                res.push_back(_vexList[u]->v);
                
                // To visit neighbors in the order they appear in the list, 
                // we should push them to the stack in reverse order.
                std::vector<ArcNode*> neighbors;
                ArcNode* curr = _vexList[u]->nextArc;
                while(curr){
                    if(!visited[curr->adjVex]) neighbors.push_back(curr);
                    curr = curr->next;
                }
                for(int i = neighbors.size() - 1; i >= 0; --i){
                    stack.push(neighbors[i]->adjVex);
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
            int u = q.pop();
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

    friend std::ostream& operator<<(std::ostream& os, const AdjacencyListGraph<VertexType>& graph) {
        os << "Adjacency Table：" << std::endl;
        for (int i = 0; i < graph._vexNum; ++i) {
            os << graph._vexList[i]->v << " ";
            ArcNode* curr = graph._vexList[i]->nextArc;
            while (curr) {
                os << "-> " << graph._vexList[curr->adjVex]->v << " " << curr->weight << " ";
                curr = curr->next;
            }
            os << "-> ^" << std::endl;
        }
        return os;
    }
};

#endif
