; query 1
; 
(set-info :status unknown)
(declare-fun r () (_ BitVec 32))
(declare-fun y () (_ BitVec 32))
(declare-fun x () (_ BitVec 32))
(assert
 (let (($x33 (= r (_ bv1 32))))
 (let (($x22 (= y (_ bv0 32))))
 (let ((?x15 (bvmul y y)))
 (let (($x16 (= ?x15 (_ bv0 32))))
 (let ((?x8 (bvmul x x)))
 (let (($x36 (bvsle ?x8 (_ bv4294967295 32))))
 (let (($x37 (not $x36)))
 (and $x37 $x16 $x22 $x33)))))))))
(check-sat)

(reset)
; query 2
; 
(set-info :status unknown)
(declare-fun r () (_ BitVec 32))
(declare-fun y () (_ BitVec 32))
(declare-fun x () (_ BitVec 32))
(assert
 (let (($x42 (= r (_ bv4294967295 32))))
 (let (($x33 (= r (_ bv1 32))))
 (let (($x22 (= y (_ bv0 32))))
 (let (($x24 (not $x22)))
 (let ((?x15 (bvmul y y)))
 (let (($x16 (= ?x15 (_ bv0 32))))
 (let ((?x8 (bvmul x x)))
 (let (($x36 (bvsle ?x8 (_ bv4294967295 32))))
 (let (($x37 (not $x36)))
 (and $x37 $x16 $x24 $x33 $x42)))))))))))
(check-sat)

(reset)
; query 3
; 
(set-info :status unknown)
(declare-fun r () (_ BitVec 32))
(declare-fun y () (_ BitVec 32))
(declare-fun x () (_ BitVec 32))
(assert
 (let (($x33 (= r (_ bv1 32))))
 (let (($x22 (= y (_ bv0 32))))
 (let ((?x15 (bvmul y y)))
 (let (($x16 (= ?x15 (_ bv0 32))))
 (let (($x18 (not $x16)))
 (let ((?x8 (bvmul x x)))
 (let (($x36 (bvsle ?x8 (_ bv4294967295 32))))
 (let (($x37 (not $x36)))
 (and $x37 $x18 $x22 $x33))))))))))
(check-sat)

(reset)
; query 4
; 
(set-info :status unknown)
(declare-fun r () (_ BitVec 32))
(declare-fun y () (_ BitVec 32))
(declare-fun x () (_ BitVec 32))
(assert
 (let (($x47 (= (bvsdiv_i (bvmul x x) (bvmul y y)) r)))
 (let (($x33 (= r (_ bv1 32))))
 (let (($x22 (= y (_ bv0 32))))
 (let (($x24 (not $x22)))
 (let ((?x15 (bvmul y y)))
 (let (($x16 (= ?x15 (_ bv0 32))))
 (let (($x18 (not $x16)))
 (let ((?x8 (bvmul x x)))
 (let (($x36 (bvsle ?x8 (_ bv4294967295 32))))
 (let (($x37 (not $x36)))
 (and $x37 $x18 $x24 $x33 $x47))))))))))))
(check-sat)

(reset)
; query 5
; 
(set-info :status unknown)
(declare-fun r () (_ BitVec 32))
(declare-fun y () (_ BitVec 32))
(declare-fun x () (_ BitVec 32))
(assert
 (let (($x33 (= r (_ bv1 32))))
 (let (($x22 (= y (_ bv0 32))))
 (let ((?x15 (bvmul y y)))
 (let (($x16 (= ?x15 (_ bv0 32))))
 (let ((?x8 (bvmul x x)))
 (let (($x36 (bvsle ?x8 (_ bv4294967295 32))))
 (and $x36 $x16 $x22 $x33))))))))
(check-sat)

(reset)
; query 6
; 
(set-info :status unknown)
(declare-fun r () (_ BitVec 32))
(declare-fun y () (_ BitVec 32))
(declare-fun x () (_ BitVec 32))
(assert
 (let (($x33 (= r (_ bv1 32))))
 (let (($x22 (= y (_ bv0 32))))
 (let (($x24 (not $x22)))
 (let ((?x15 (bvmul y y)))
 (let (($x16 (= ?x15 (_ bv0 32))))
 (let ((?x8 (bvmul x x)))
 (let (($x36 (bvsle ?x8 (_ bv4294967295 32))))
 (and $x36 $x16 $x24 $x33)))))))))
(check-sat)

(reset)
; query 7
; 
(set-info :status unknown)
(declare-fun r () (_ BitVec 32))
(declare-fun y () (_ BitVec 32))
(declare-fun x () (_ BitVec 32))
(assert
 (let (($x33 (= r (_ bv1 32))))
 (let (($x22 (= y (_ bv0 32))))
 (let ((?x15 (bvmul y y)))
 (let (($x16 (= ?x15 (_ bv0 32))))
 (let (($x18 (not $x16)))
 (let ((?x8 (bvmul x x)))
 (let (($x36 (bvsle ?x8 (_ bv4294967295 32))))
 (and $x36 $x18 $x22 $x33)))))))))
(check-sat)

(reset)
; query 8
; 
(set-info :status unknown)
(declare-fun r () (_ BitVec 32))
(declare-fun y () (_ BitVec 32))
(declare-fun x () (_ BitVec 32))
(assert
 (let (($x47 (= (bvsdiv_i (bvmul x x) (bvmul y y)) r)))
 (let (($x33 (= r (_ bv1 32))))
 (let (($x22 (= y (_ bv0 32))))
 (let (($x24 (not $x22)))
 (let ((?x15 (bvmul y y)))
 (let (($x16 (= ?x15 (_ bv0 32))))
 (let (($x18 (not $x16)))
 (let ((?x8 (bvmul x x)))
 (let (($x36 (bvsle ?x8 (_ bv4294967295 32))))
 (and $x36 $x18 $x24 $x33 $x47)))))))))))
(check-sat)
