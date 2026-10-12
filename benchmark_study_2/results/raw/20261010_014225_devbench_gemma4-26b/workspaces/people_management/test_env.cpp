#include <iostream>
#include <string>
#include <vector>

int main() {
    std::string test_str = "hello";
    std::vector<std::string> test_vec = {"hello", "world"};
    
    std::cout << "String test: " << test_str << std::endl;
    for (const auto& s : test_vec) {
        std::cout << "Vector element: " << s << std::endl;
    }
    
    return 0;
}
