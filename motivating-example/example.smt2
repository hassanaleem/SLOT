(set-logic QF_BV)
(declare-const x (_ BitVec 32))
(declare-const y (_ BitVec 32))
(declare-const r (_ BitVec 32))

(assert
  (ite (= y #x00000000)
       (= r #x00000001)
       (= r (bvsdiv (bvmul x x) (bvmul y y)))))

(assert (= r #x00000001))
(check-sat)