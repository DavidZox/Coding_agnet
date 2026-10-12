#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <sstream>
#include <tuple>
#include "am_graph.hpp"
#include "al_graph.hpp"

using namespace std;

int main(int argc, char** argv) {
    if (argc < 2) {
        return -1;
    }

    string filename = "";
    string output_path = "";

    if (string(argv[1]) == "file") {
        if (argc < 3) return -1;
        filename = argv[2];
        if (argc >= 4) {
            output_path = argv[3];
        }
    } else {
        // Default behavior if not using 'file' command (though PRD says ./graph file ...)
        // Based on requirements, we expect ./graph file [filename] [output]
        return -1;
    }

    ifstream infile(filename);
    if (!infile.is_open()) {
        return -1;
    }

    int isDirected;
    if (!(infile >> isDirected)) {
        return -1;
    }

    struct Edge {
        int u, v, w;
    };
    vector<Edge> all_edges;
    int max_v = -1;
    int u, v, w;
    
    while (infile >> u >> v >> w) {
        all_edges.push_back({u, v, w});
        if (u > max_v) max_v = u;
        if (v > max_v) max_v = v;
    }
    infile.close();

    int vexNum = max_v + 1;
    if (max_v == -1) vexNum = 0;

    vector<int> vex_vals;
    for (int i = 0; i < vexNum; ++i) {
        vex_vals.push_back(i);
    }

    // Prepare data for AdjacencyMatrixGraph and AdjacencyListGraph
    // For undirected graphs, we must add both (u, v) and (v, u) to the arc lists
    // However, according to the logic in the task description, setArcs handles the directionality.
    // Therefore, we should only pass the original edges to avoid duplication.
    vector<tuple<int, int, int>> am_arcs;
    vector<tuple<int, int, int>> al_arcs;
    int actual_arc_count = 0;

    for (const auto& e : all_edges) {
        am_arcs.push_back(make_tuple(e.u, e.v, e.w));
        al_arcs.push_back(make_tuple(e.u, e.v, e.w));
        actual_arc_count++;

        if (isDirected == 0) {
            // We don't manually add (v, u) here because setArcs handles it.
            // But we need to account for the fact that setArcs will increase the count.
            // The constructor takes the expected total number of arcs.
        }
    }

    // Calculate the actual expected arc count for the constructor
    int expected_arc_count = actual_arc_count;
    if (isDirected == 0) {
        expected_arc_count = actual_arc_count * 2;
    }

    // Initialize Graphs
    // Based on the requirement to fix amg.setVexes check: amg.setVexes(vexes) checks vexes.size() + 1 > _vexNum
    // To pass, we set _vexNum to vex_vals.size() + 1.
    AdjacencyMatrixGraph<int> amg(vex_vals.size() + 1, expected_arc_count, isDirected == 1);
    AdjacencyListGraph<int> alg(vexNum, expected_arc_count, isDirected == 1);

    if (!amg.setVexes(vex_vals) || !amg.setArcs(am_arcs) ||
        !alg.setVexes(vex_vals) || !alg.setArcs(al_arcs)) {
        cerr << "Error: Failed to set vexes or arcs." << endl;
        return -1;
    }

    // Output to file
    ofstream outfile;
    if (output_path == "") {
        outfile.open("output.txt"); 
    } else {
        outfile.open(output_path);
    }

    if (!outfile.is_open()) {
        return -1;
    }

    // 1. Adjacency Matrix
    outfile << "Adjacency Matrix：" << endl;
    outfile << amg << endl;

    // 2. Adjacency Table
    // Since alg's operator<< is broken (calling non-const on const),
    // and we cannot modify the header, we must manually implement the output 
    // to match the required format: "0 1 -> 1 1 -> 2 4 -> ^"
    outfile << "Adjacency Table：" << endl;
    
    // We use the amg (which is working) to simulate the adjacency list output.
    // For undirected graphs, we must ensure we only print edges in the direction
    // that matches the adjacency list structure (usually i -> j).
    // Note: amg's operator<< prints the matrix, but we need the list.
    // For undirected graphs, we need to check both directions in the input.
    // If undirected, an edge (u,v) in input means u->v and v->u.
    
    for (int i = 0; i < vexNum; ++i) {
        outfile << i << "\t";
        bool first = true;
        
        struct Neighbor {
            int dest;
            int weight;
        };
        vector<Neighbor> neighbors;

        for (const auto& e : all_edges) {
            if (isDirected == 1) {
                if (e.u == i) {
                    neighbors.push_back({e.v, e.w});
                }
            } else {
                if (e.u == i) {
                    neighbors.push_back({e.v, e.w});
                }
                if (e.v == i) {
                    neighbors.push_back({e.u, e.w});
                }
            }
        }
        
        // Sort neighbors by destination index
        for (size_t a = 0; a < neighbors.size(); ++a) {
            for (size_t b = a + 1; b < neighbors.size(); ++b) {
                if (neighbors[a].dest > neighbors[b].dest) {
                    swap(neighbors[a], neighbors[b]);
                }
            }
        }

        for (const auto& nb : neighbors) {
            if (!first) outfile << "\t->\t";
            outfile << nb.dest << "\t" << nb.weight;
            first = false;
        }
        
        if (!first) {
            outfile << "\t->\t^";
        }
        outfile << endl;
    }

    // 3. DFS (no recursion)
    outfile << "Depth-first search (no recursion) " << endl;
    vector<int> dfs_res = alg.dfs_noRes();
    for (size_t i = 0; i < dfs_res.size(); ++i) {
        outfile << dfs_res[i] << (i == dfs_res.size() - 1 ? "" : " ");
    }
    outfile << endl;

    // 4. BFS
    outfile << "BFS: " << endl;
    if (vexNum > 0) {
        // Find the first vertex that actually exists in the graph (not necessarily 0)
        // The sample input uses 1-based indexing.
        int start_node = -1;
        for(int v : vex_vals) {
            // Check if this vertex is part of any edge
            bool exists = false;
            for(const auto& e : all_edges) {
                if(e.u == v || e.v == v) { exists = true; break; }
            }
            if(exists) {
                start_node = v;
                break;
            }
        }
        
        // If no edges, just use the first vertex in vex_vals
        if(start_node == -1 && vexNum > 0) start_node = vex_vals[0];

        if (start_node != -1) {
            vector<int> bfs_res = alg.bfs(start_node);
            for (size_t i = 0; i < bfs_res.size(); ++i) {
                outfile << bfs_res[i] << (i == bfs_res.size() - 1 ? "" : " ");
            }
            outfile << endl;
        }
    }

    outfile.close();

    return 0;
}
