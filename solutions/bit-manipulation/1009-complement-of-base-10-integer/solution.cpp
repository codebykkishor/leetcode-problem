class Solution {
public:
    int bitwiseComplement(int n) {

 // Special case: If n is 0, its complement is 1.
        if (n == 0) return 1;

        int mask = 0, temp = n;

        // Create a mask with all bits set to 1 for the length of n in binary.
        while (temp > 0) {
            mask = (mask << 1) | 1; // Shift left and add 1 to mask
            temp >>= 1; // Reduce temp by dividing by 2
        }

        // Perform XOR with the mask to get the complement
        return (~n) & mask;
    }
        
    
};
