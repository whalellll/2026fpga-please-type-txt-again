function integer tile_bias(input integer index);
begin
case(index)
0: tile_bias=32'sd20206;
1: tile_bias=32'sd18900;
2: tile_bias=32'sd6371;
3: tile_bias=32'sd4794;
4: tile_bias=32'sd6627;
5: tile_bias=32'sd53960;
6: tile_bias=32'sd48810;
7: tile_bias=-32'sd33644;
8: tile_bias=32'sd9117;
9: tile_bias=32'sd34689;
10: tile_bias=32'sd54909;
11: tile_bias=32'sd6345;
12: tile_bias=32'sd18991;
13: tile_bias=32'sd19245;
14: tile_bias=32'sd8244;
15: tile_bias=32'sd7724;
default: tile_bias=0;
endcase
end
endfunction
