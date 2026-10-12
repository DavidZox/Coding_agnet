#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <sstream>
#include <tuple>
#include <algorithm>
#include "../include/al_graph.hpp"
#include "../include/am_graph.hpp"

/**
 * The main function serves as the entry point.
 * It parses command line arguments, reads graph data from a file,
 * initializes AdjacencyListGraph and AdjacencyMatrixGraph,
 * and outputs the required information to the specified output file.
 */
int main(int argc, char** argv) {
    if (argc < 2) {
        return -1;
    }

    std::string mode = argv[1];
    std::string input_filename;
    std::string output_filename;

    if (mode == "file") {
        if (argc < 3) return -1;
        input_filename = argv[2];
        if (argc >= 4) {
            output_filename = argv[3];
        } else {
            // If no output file path is provided, we can't satisfy the requirement 
            // of writing to [output file path]. However, for standard behavior, 
            // we'll assume the user must provide it or we default to stdout.
            // Based on PRD: "the output file can be found in [output file path]".
            return -1; 
        }
    } else {
        // Default data mode (though PRD implies file mode is the primary use case)
        return -1;
    }

    std::ifstream infile(input_filename);
    if (!infile.is_open()) {
        return -1;
    }

    int isDirectedInt;
    if (!(infile >> isDirectedInt)) return -1;
    bool isDirected = (isDirectedInt == 1);

    // First pass: read all edges to determine number of vertices and arcs
    // Since the input format doesn't specify V and E explicitly, 
    // we must infer V from the max vertex index found.
    struct Edge {
        int u, v, w;
    };
    std::vector<Edge> edges;
    int maxV = -1;
    int u, v, w;
    while (infile >> u >> v >> w) {
        edges.push_back({u, v, w});
        if (u > maxV) maxV = u;
        if (v > maxV) maxV = v;
    }
    infile.close();

    int vexNum = maxV + 1;
    int arcNum = edges.size();
    if (!isDirected) {
        // For undirected, the number of arcs in the matrix/list context 
        // is often treated as the number of unique pairs, but the 
        // setArcs logic in the provided headers handles the doubling.
    }

    // Prepare data for graphs
    std::vector<int> vexList;
    for (int i = 0; i < vexNum; ++i) {
        vexList.push_back(i);
    }

    std::vector<std::tuple<int, int, int>> arcTuples;
    for (const auto& e : edges) {
        arcTuples.push_back(std::make_tuple(e.u, e.v, e.w));
    }

    // Initialize Graphs
    // Note: AdjacencyMatrixGraph constructor takes (vexNum, arcNum, isDirected)
    // The UML/Architecture suggests vexNum+1 for AMG in sequence diagram, 
    // but the header uses vexNum. We follow the header implementation.
    AdjacencyMatrixGraph<int> amg(vexNum, arcNum, isDirected);
    AdjacencyListGraph<int> alg(vexNum, arcNum, isDirected);

    if (!amg.setVexes(vexList) || !amg.setArcs(arcTuples) ||
        !alg.setVexer(vexList) || !alg.setArcs(arcTuples)) {
        return -1;
    }

    // Prepare Output
    std::ofstream outfile(output_filename);
    if (!outfile.is_open()) {
        return -1;
    }

    // 1. Adjacency Matrix
    outfile << "Adjacency Matrix：" << std::endl;
    outfile << amg;

    // 2. Adjacency Table
    outfile << "Adjacency Table：" << std::endl;
    outfile << alg;

    // 3. DFS (no recursion)
    outfile << "Depth-first search (no recursion) " << std::endl;
    std::vector<int> dfs_res = alg.dfs_noRes();
    for (size_t i = 0; i < dfs_res.size(); ++i) {
        outfile << dfs_res[i] << (i == dfs_res.size() - 1 ? "" : " ");
    }
    outfile << " " << std::endl;

    // 4. BFS
    outfile << "BFS: " << std::endl;
    std::vector<int> bfs_res = alg.bfs();
    for (size_t i = 0; i < bfs_res.size(); ++i) {
        outfile << bfs_res[i] << (i == bfs_res.size() - 1 ? "" : " ");
    }
    outfile << " " << std::endl;

    outfile.close();

    return 0;
}
