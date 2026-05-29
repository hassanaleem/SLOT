; query 1
; 
(set-info :status unknown)
(declare-fun b () (_ BitVec 32))
(declare-fun a () (_ BitVec 32))
(assert
 (let (($x25 (not (= (bvudiv_i (bvmul a b) a) b))))
 (let (($x26 (not (or (= a (_ bv0 32)) (= b (_ bv0 32))))))
 (let (($x8 (= a (_ bv0 32))))
 (and $x8 $x26 $x25)))))
(check-sat)

(reset)
; query 2
; 
(set-info :status unknown)
(declare-fun a () (_ BitVec 32))
(declare-fun b () (_ BitVec 32))
(assert
 (let (($x30 (bvule b (bvudiv_i (_ bv4294967295 32) a))))
 (let (($x25 (not (= (bvudiv_i (bvmul a b) a) b))))
 (let (($x26 (not (or (= a (_ bv0 32)) (= b (_ bv0 32))))))
 (let (($x8 (= a (_ bv0 32))))
 (let (($x10 (not $x8)))
 (and $x10 $x26 $x25 $x30)))))))
(check-sat)
