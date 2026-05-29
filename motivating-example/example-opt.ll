; ModuleID = '../motivating-example/example.smt2'
source_filename = "../motivating-example/example.smt2"

define i1 @SMT(i32 %x, i32 %y, i32 %r) {
b:
  %0 = mul i32 %y, %y
  %1 = mul i32 %x, %x
  %2 = sdiv i32 %1, %0
  %.inv = icmp sgt i32 %1, -1
  br i1 %.inv, label %b.TrueSelect, label %b.FalseSelect

b.TrueSelect:                                     ; preds = %b
  br label %b.AfterSelect

b.FalseSelect:                                    ; preds = %b
  br label %b.AfterSelect

b.AfterSelect:                                    ; preds = %b.FalseSelect, %b.TrueSelect
  %3 = phi i32 [ -1, %b.TrueSelect ], [ 1, %b.FalseSelect ]
  %4 = icmp eq i32 %0, 0
  br i1 %4, label %b.AfterSelect.TrueSelect, label %b.AfterSelect.FalseSelect

b.AfterSelect.TrueSelect:                         ; preds = %b.AfterSelect
  br label %b.AfterSelect.AfterSelect

b.AfterSelect.FalseSelect:                        ; preds = %b.AfterSelect
  br label %b.AfterSelect.AfterSelect

b.AfterSelect.AfterSelect:                        ; preds = %b.AfterSelect.FalseSelect, %b.AfterSelect.TrueSelect
  %5 = phi i32 [ %3, %b.AfterSelect.TrueSelect ], [ %2, %b.AfterSelect.FalseSelect ]
  %6 = icmp eq i32 %5, %r
  %7 = icmp eq i32 %r, 1
  %8 = icmp eq i32 %y, 0
  br i1 %8, label %b.AfterSelect.AfterSelect.TrueSelect, label %b.AfterSelect.AfterSelect.FalseSelect

b.AfterSelect.AfterSelect.TrueSelect:             ; preds = %b.AfterSelect.AfterSelect
  br label %b.AfterSelect.AfterSelect.AfterSelect

b.AfterSelect.AfterSelect.FalseSelect:            ; preds = %b.AfterSelect.AfterSelect
  br label %b.AfterSelect.AfterSelect.AfterSelect

b.AfterSelect.AfterSelect.AfterSelect:            ; preds = %b.AfterSelect.AfterSelect.FalseSelect, %b.AfterSelect.AfterSelect.TrueSelect
  %9 = phi i1 [ %7, %b.AfterSelect.AfterSelect.TrueSelect ], [ %6, %b.AfterSelect.AfterSelect.FalseSelect ]
  %10 = and i1 %7, %9
  ret i1 %10
}
