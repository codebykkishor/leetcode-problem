class Solution {
public:
    int lengthOfLongestSubstring(string S) {
        

        vector<bool>count(256,0);
        int first = 0, second = 0, len=0;

        while(second < S.size()){
            // repeating char

            while(count[S[second]]){
                count[S[first]]=0;
                first++;
            }

            count[S[second]]=1;
            len = max(len,second-first+1);
            second++;
        }
        return len;
    }
};
