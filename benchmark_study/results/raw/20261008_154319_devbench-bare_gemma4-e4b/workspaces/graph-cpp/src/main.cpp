#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <sstream>
#include <tuple>
#include <algorithm>
#include <stdexcept>

#include "al_graph.hpp"
#include "am_graph.hpp"

using namespace std;

// Helper function to read graph data from a file
// Returns: {is_directed, vector_of_vertices, vector_of_arcs}
tuple<bool, vector<int>, vector<tuple<int, int, int>>> readGraphFromFile(const string& filename) {
    ifstream file(filename);
    if (!file.is_open()) {
        throw runtime_error("Could not open input file: " + filename);
    }

    string line;
    
    // Read first line: directed status (0=undirected, 1=directed)
    if (!getline(file, line)) {
        throw runtime_error("Input file is empty.");
    }
    int is_directed_int;
    stringstream ss_dir(line);
    ss_dir >> is_directed_int;
    bool is_directed = (is_directed_int == 1);

    // We need to determine the number of vertices first. 
    // Since the file format only gives edges, we must read all edges first to find all unique vertices.
    vector<tuple<int, int, int>> raw_arcs;
    vector<int> vertices_set;
    
    // Read remaining lines (edges)
    while (getline(file, line)) {
        if (line.empty()) continue;
        stringstream ss_edge(line);
        int u, v, w;
        if (ss_edge >> u >> v >> w) {
            raw_arcs.emplace_back(u, v, w);
            
            // Collect unique vertices
            if (find(vertices_set.begin(), vertices_set.end(), u) == vertices_set.end()) {
                vertices_set.push_back(u);
            }
            if (find(vertices_set.begin(), vertices_set.end(), v) == vertices_set.end()) {
                vertices_set.push_back(v);
            }
        }
    }

    // Sort and unique the vertices to establish a consistent mapping (0 to N-1)
    sort(vertices_set.begin(), vertices_set.end());
    vertices_set.erase(unique(vertices_set.begin(), vertices_set.end()), vertices_set.end());

    // Map original vertex IDs to 0-based indices
    int num_vertices = vertices_set.size();
    
    // Reformat arcs to use 0-based indices
    vector<tuple<int, int, int>> indexed_arcs;
    for (const auto& arc : raw_arcs) {
        int u_orig = get<0>(arc);
        int v_orig = get<1>(arc);
        int w = get<2>(arc);

        // Find indices (assuming vertices_set contains all relevant vertices)
        auto find_index = [&](int val) -> int {
            for (int i = 0; i < num_vertices; ++i) {
                if (vertices_set[i] == val) return i;
            }
            return -1; // Should not happen if vertices_set was built correctly
        };

        int u_idx = find_index(u_orig);
        int v_idx = find_index(v_orig);

        if (u_idx != -1 && v_idx != -1) {
            indexed_arcs.emplace_back(u_idx, v_idx, w);
        }
    }

    return make_tuple(is_directed, vertices_set, indexed_arcs);
}


void printAdjacencyMatrix(const AdjacencyMatrixGraph<int>& amg) {
    cout << "\nAdjacency Matrix：\n";
    // The operator<< for AMG already prints the matrix format required
    cout << amg;
}

void printAdjacencyTable(const AdjacencyListGraph<int>& alg) {
    cout << "\nAdjacency Table：\n";
    
    // Since ALG uses original vertex types (which are ints in this context, representing indices 0..N-1),
    // we need to iterate through the structure to print the table format.
    // We rely on the fact that the vertex list in ALG corresponds to indices 0..N-1.
    
    // We need to access internal structure or rely on a custom print method.
    // Since the UML suggests friend operator<<, we'll use that for the structure, 
    // but the PRD requires a specific tabular format. We must manually reconstruct the table output based on the structure.
    
    // For simplicity and adherence to the required output format, we will print the structure 
    // based on the indices 0 to N-1, assuming the vertex list in ALG is [0, 1, 2, ... N-1].
    
    // NOTE: The provided ALG implementation does not expose a simple way to print the table format 
    // (e.g., "0 1 -> 1 1 -> 2 4 -> ^"). We must simulate this based on the graph structure.
    
    // We will use a simplified representation that mimics the required structure if direct access is impossible.
    // Given the constraints, we assume the vertex list in ALG is 0, 1, 2, ... N-1.
    
    // We iterate through vertices (indices)
    for (int i = 0; i < alg._vexNum; ++i) {
        cout << alg._vexes[i] << "\t";
        
        // Print neighbors for vertex i
        ArcNode* currentArc = alg._adjList[i];
        vector<pair<int, int>> neighbors_info; // {neighbor_index, weight}
        while (currentArc) {
            neighbors_info.push_back({currentArc->adjVex, currentArc->weight});
            currentArc = currentArc->next;
        }
        
        // Sort neighbors by index for consistent output order
        sort(neighbors_info.begin(), neighbors_info.end(), [](const auto& a, const auto& b) {
            return a.first < b.first;
        });

        for (size_t j = 0; j < neighbors_info.size(); ++j) {
            int v_idx = neighbors_info[j].first;
            int weight = neighbors_info[j].second;
            
            cout << alg._vexes[v_idx] << " -> " << weight;
            if (j < neighbors_info.size() - 1) {
                cout << "\t";
            }
        }
        cout << "\t^" << endl;
    }
}

void printTraversalResults(const AdjacencyListGraph<int>& alg) {
    // DFS
    vector<int> dfs_seq = alg.dfs_noRes();
    cout << "\nDepth-first search (no recursion) \n";
    for (size_t i = 0; i < dfs_seq.size(); ++i) {
        cout << dfs_seq[i] << (i == dfs_seq.size() - 1 ? "" : " ");
    }
    cout << endl;

    // BFS
    vector<int> bfs_seq = alg.bfs();
    cout << "BFS: \n";
    for (size_t i = 0; i < bfs_seq.size(); ++i) {
        cout << bfs_seq[i] << (i == bfs_seq.size() - 1 ? "" : " ");
    }
    cout << endl;
}


int main(int argc, char** argv) {
    if (argc < 3 || (argc == 3 && string(argv[1]) != "file")) {
        cerr << "Usage: ./graph file <input_filename> <output_filename>" << endl;
        return 1;
    }

    string mode = argv[1];
    string input_file = argv[2];
    string output_file = argv[3];

    try {
        // 1. Read Graph Data
        auto [is_directed, vertices, arcs] = readGraphFromFile(input_file);

        // 2. Initialize and Set up Graphs
        int num_vertices = vertices.size();
        int num_arcs = arcs.size();

        // Initialize ALG (using int for VertexType as per file reading)
        AdjacencyListGraph<int> alg(num_vertices, num_arcs, is_directed);
        
        // Set vertices for ALG
        if (!alg.setVexes(vertices)) {
            throw runtime_error("Failed to set vertices for ALG.");
        }
        // Set arcs for ALG
        if (!alg.setArcs(arcs)) {
            throw runtime_error("Failed to set arcs for ALG.");
        }

        // Initialize AMG (Note: AMG constructor expects N+1, M+1 based on sequence diagram, 
        // but since we are using 0-based indexing derived from input, we use N for both dimensions)
        // We use N for both dimensions as the vertex indices are 0 to N-1.
        AdjacencyMatrixGraph<int> amg(num_vertices, num_arcs, is_directed);
        
        // Set vertices for AMG
        if (!amg.setVexes(vertices)) {
            throw runtime_error("Failed to set vertices for AMG.");
        }
        // Set arcs for AMG (Note: AMG expects 0-based indices for arcs)
        if (!amg.setArcs(arcs)) {
            throw runtime_error("Failed to set arcs for AMG.");
        }

        // 3. Output Results to File
        ofstream outfile(output_file);
        if (!outfile.is_open()) {
            throw runtime_error("Could not open output file: " + output_file);
        }

        // Output 1: Adjacency Matrix
        outfile << "\nAdjacency Matrix：\n";
        // Manually print matrix to match required format exactly
        for (int i = 0; i < num_vertices; ++i) {
            for (int j = 0; j < num_vertices; ++j) {
                outfile << amg.arcMatrix[i][j] << (j == num_vertices - 1 ? "" : " ");
            }
            outfile << "\n";
        }

        // Output 2: Adjacency Table
        outfile << "\nAdjacency Table：\n";
        // Manually print table to match required format exactly
        for (int i = 0; i < num_vertices; ++i) {
            outfile << alg._vexes[i] << "\t";
            
            ArcNode* currentArc = alg._adjList[i];
            vector<pair<int, int>> neighbors_info; // {neighbor_index, weight}
            while (currentArc) {
                neighbors_info.push_back({currentArc->adjVex, currentArc->weight});
                currentArc = currentArc->next;
            }
            
            sort(neighbors_info.begin(), neighbors_info.end(), [](const auto& a, const auto& b) {
                return a.first < b.first;
            });

            for (size_t j = 0; j < neighbors_info.size(); ++j) {
                int v_idx = neighbors_info[j].first;
                int weight = neighbors_info[j].second;
                
                outfile << alg._vexes[v_idx] << " -> " << weight;
                if (j < neighbors_info.size() - 1) {
                    outfile << "\t";
                }
            }
            outfile << "\t^" << "\n";
        }


        // Output 3: Traversal Results
        outfile << "\nDepth-first search (no recursion) \n";
        vector<int> dfs_seq = alg.dfs_noRes();
        for (size_t i = 0; i < dfs_seq.size(); ++i) {
            outfile << dfs_seq[i] << (i == dfs_seq.size() - 1 ? "" : " ");
        }
        outfile << "\n";

        outfile << "BFS: \n";
        vector<int> bfs_seq = alg.bfs();
        for (size_t i = 0; i < bfs_seq.size(); ++i) {
            outfile << bfs_seq[i] << (i == bfs_seq.size() - 1 ? "" : " ");
        }
        outfile << "\n";

        outfile.close();
        cout << "Successfully processed graph and saved output to: " << output_file << endl;

    } catch (const runtime_error& e) {
        cerr << "Error: " << e.what() << endl;
        return 1;
    } catch (const exception& e) {
        cerr << "An unexpected error occurred: " << e.what() << endl;
        return 1;
    }

    return 0;
}
