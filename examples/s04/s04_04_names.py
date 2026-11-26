def is_free_shipping(subtotal):
    return subtotal >= 5000


print(is_free_shipping(3600))
print(is_free_shipping(6000))
if is_free_shipping(6000):
    print("送料無料です")
