#ifndef AL_GRAPH_HPP
#define AL_GRAPH_HPP

#include <vector>
#include <tuple>
#include <iostream>
#include <map>
#include <algorithm>

// Forward declarations for Queue and Stack if needed, but for now, we assume they are available or defined later.
// Since we are only implementing al_graph.hpp, we will use standard types and assume necessary includes for vector/tuple/iostream.

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

    // Using a map to store the head of the adjacency list for each vertex index
    std::map<int, ArcNode*> _adjLists;
    std::vector<VertexType> _vexes; // Stores the actual vertex values mapped to indices

    // Helper to get the index of a vertex value
    int locateVexInternal(const VertexType& value) const {
        for (size_t i = 0; i < _vexes.size(); ++i) {
            if (_vexes[i] == value) {
                return static_cast<int>(i);
            }
        }
        return -1; // Not found
    }

public:
    // Constructor
    AdjacencyListGraph(bool isDirected, int numVexes, int numArcs)
        : _isDirected(isDirected), _vexNum(numVexes), _arcNum(numArcs) {}

    // Destructor to clean up dynamically allocated ArcNodes
    ~AdjacencyListGraph() {
        for (auto const& [key, head] : _adjLists) {
            ArcNode* current = head;
            while (current != nullptr) {
                ArcNode* next = current->next;
                delete current;
                current = next;
            }
        }
    }

    // Set vertices
    bool setVexes(std::vector<VertexType>& vexes) {
        _vexes = vexes;
        _vexNum = vexes.size();
        _adjLists.clear();
        return true; // Assuming success for simplicity based on PRD/UML, actual error handling might be more complex
    }

    // Set arcs
    // Input format: vector of tuples {start_vertex, end_vertex, weight}
    bool setArcs(const std::vector<std::tuple<VertexType, VertexType, int>>& arcs) {
        _arcNum = arcs.size();
        _adjLists.clear();

        for (const auto& arc : arcs) {
            VertexType u_val = std::get<0>(arc);
            VertexType v_val = std::get<1>(arc);
            int weight = std::get<2>(arc);

            int u_idx = locateVexInternal(u_val);
            int v_idx = locateVexInternal(v_val);

            if (u_idx == -1 || v_idx == -1) {
                return false; // Vertex not found
            }

            // Create new arc node
            ArcNode* newNode = new ArcNode(v_idx, weight);

            // Insert at the beginning of u's adjacency list
            if (_adjLists.find(u_idx) == _adjLists.end()) {
                _adjLists[u_idx] = nullptr;
            }
            newNode->next = _adjLists[u_idx];
            _adjLists[u_idx] = newNode;

            // If undirected, add the reverse edge
            if (!_isDirected) {
                ArcNode* reverseNode = new ArcNode(u_idx, weight);
                if (_adjLists.find(v_idx) == _adjLists.end()) {
                    _adjLists[v_idx] = nullptr;
                }
                reverseNode->next = _adjLists[v_idx];
                _adjLists[v_idx] = reverseNode;
            }
        }
        return true;
    }

    // Locate vertex index
    int locateVex(const VertexType& value) const {
        return locateVexInternal(value);
    }

    // DFS Traversal (Non-Recursive)
    std::vector<VertexType> dfs_noRes() const {
        std::vector<VertexType> result;
        if (_vexNum == 0) return result;

        std::vector<bool> visited(_vexNum, false);
        std::vector<int> stack; // Using vector as stack implementation

        // Start from the first vertex index (assuming connected graph or starting from index 0)
        int start_node_idx = 0; 
        
        // Find the first vertex that exists in _vexes
        for(int i = 0; i < _vexNum; ++i) {
            if (_vexes[i] != VertexType{}) { // Simple check if vertex exists
                start_node_idx = i;
                break;
            }
        }

        if (start_node_idx == -1) return result;

        stack.push_back(start_node_idx);
        visited[start_node_idx] = true;

        while (!stack.empty()) {
            int u_idx = stack.back();
            stack.pop_back();
            
            result.push_back(_vexes[u_idx]);

            // Get neighbors of u_idx
            ArcNode* current = _adjLists.count(u_idx) ? _adjLists.at(u_idx) : nullptr;
            
            // Iterate through neighbors in reverse order to maintain standard DFS behavior 
            // (if we want to process smaller indices first, which is typical)
            std::vector<int> neighbors;
            while (current != nullptr) {
                neighbors.push_back(current->adjVex);
                current = current->next;
            }
            std::reverse(neighbors.begin(), neighbors.end()); // Process in increasing index order

            for (int v_idx : neighbors) {
                if (!visited[v_idx]) {
                    visited[v_idx] = true;
                    stack.push_back(v_idx);
                }
            }
        }
        return result;
    }

    // BFS Traversal
    std::vector<VertexType> bfs() const {
        std::vector<VertexType> result;
        if (_vexNum == 0) return result;

        std::vector<bool> visited(_vexNum, false);
        // Using vector as queue implementation
        std::vector<int> queue_vec; 

        // Start from the first vertex index
        int start_node_idx = 0;
        for(int i = 0; i < _vexNum; ++i) {
            if (_vexes[i] != VertexType{}) {
                start_node_idx = i;
                break;
            }
        }

        if (start_node_idx == -1) return result;

        queue_vec.push_back(start_node_idx);
        visited[start_node_idx] = true;

        while (!queue_vec.empty()) {
            int u_idx = queue_vec.front();
            queue_vec.erase(queue_vec.begin()); // Dequeue
            
            result.push_back(_vexes[u_idx]);

            // Get neighbors of u_idx
            ArcNode* current = _adjLists.count(u_idx) ? _adjLists.at(u_idx) : nullptr;
            
            std::vector<int> neighbors;
            while (current != nullptr) {
                neighbors.push_back(current->adjVex);
                current = current->next;
            }
            std::sort(neighbors.begin(), neighbors.end()); // Process in increasing index order

            for (int v_idx : neighbors) {
                if (!visited[v_idx]) {
                    visited[v_idx] = true;
                    queue_vec.push_back(v_idx); // Enqueue
                }
            }
        }
        return result;
    }


    // Overload for BFS starting from a specific vertex (as per UML)
    std::vector<VertexType> bfs(const VertexType& startVertex) const {
        int start_idx = locateVexInternal(startVertex);
        if (start_idx == -1) return {};

        std::vector<VertexType> result;
        std::vector<bool> visited(_vexNum, false);
        std::vector<int> queue_vec; 

        queue_vec.push_back(start_idx);
        visited[start_idx] = true;

        while (!queue_vec.empty()) {
            int u_idx = queue_vec.front();
            queue_vec.erase(queue_vec.begin());
            
            result.push_back(_vexes[u_idx]);

            ArcNode* current = _adjLists.count(u_idx) ? _adjLists.at(u_idx) : nullptr;
            
            std::vector<int> neighbors;
            while (current != nullptr) {
                neighbors.push_back(current->adjVex);
                current = current->next;
            }
            std::sort(neighbors.begin(), neighbors.end());

            for (int v_idx : neighbors) {
                if (!visited[v_idx]) {
                    visited[v_idx] = true;
                    queue_vec.push_back(v_idx);
                }
            }
        }
        return result;
    }


    // Friend operator<< for printing the graph structure (Adjacency List representation)
    friend std::ostream& operator<<(std::ostream& os, const AdjacencyListGraph<VertexType>& graph) {
        os << "Adjacency Table：\n";
        
        // Print header row (Vertex values)
        os << " ";
        for (const auto& v : graph._vexes) {
            os << v << "\t";
        }
        os << "\n";

        // Print data rows
        for (int i = 0; i < graph._vexNum; ++i) {
            os << graph._vexes[i] << "\t";
            
            ArcNode* current = graph._adjLists.count(i) ? graph._adjLists.at(i) : nullptr;
            
            // Collect neighbors for this vertex i
            std::vector<std::pair<int, int>> neighbors_data; // {adjVex, weight}
            while (current != nullptr) {
                neighbors_data.push_back({current->adjVex, current->weight});
                current = current->next;
            }
            
            // Sort neighbors by index for consistent output
            std::sort(neighbors_data.begin(), neighbors_data.end(), [](const auto& a, const auto& b) {
                return a.first < b.first;
            });

            // Print neighbors
            for (const auto& neighbor : neighbors_data) {
                os << neighbor.first << "->" << neighbor.second << "\t";
            }
        }
        os << "\n";
        return os;
    }
};

#endif // AL_GRAPH_HPP
