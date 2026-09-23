class Solution {
public:
    bool isPalindrome(int z) {
       // int z = abs(x);

        int rem;
        long long ans =0;
        int ori= z;

        while(z > 0){
            rem = z %10;
            ans = (ans *10)+rem;
            // if(ans>INT_MAX/10 || ans<INT_MIN)
            // return 0;

            z = z/10;
        }

        return ori == ans;

        
    }
};
